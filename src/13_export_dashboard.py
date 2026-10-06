"""대시보드용 JSON 내보내기 (단계 8.1). 파일 표는 docs/SPEC.md 3.17절 표 15.

검증셋(monitor_val.parquet, alerts_val.parquet)에서 리플레이·경보 카드·성능 비교·불펜 부하를 만들고, 아직 결과가 없는 고교·KBO는
가상 데이터로 만들어 meta.json의 synthetic 목록에 적는다. 실명·원데이터 행은 넣지 않는다(고교는 가명 코드만, MLB 선수 이름은 공개 기록).

사용 예:
    python -m src.13_export_dashboard
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from datetime import date, datetime

import numpy as np
import pandas as pd

from src.common import calibration as cal
from src.common import highschool as hs
from src.common import metrics as mt
from src.common.config import ROOT, load_config

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
OUT = ROOT / "dashboard-web" / "public" / "data"
SPLIT = "val"
SIGNALS = {"velo": "구속 하락 신호", "change": "폼 변화 신호"}
log = logging.getLogger("pitchsignal.export")


def dump(name: str, payload) -> int:
    path = OUT / name
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default), encoding="utf-8")
    return path.stat().st_size


def _json_default(value):
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else round(float(value), 3)
    if isinstance(value, np.bool_):
        return bool(value)
    raise TypeError(str(type(value)))


def r3(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 3)


def pick_replay(cfg: dict, monitor: pd.DataFrame, cases: pd.DataFrame, controls: pd.DataFrame, windows: pd.DataFrame) -> pd.DataFrame:
    """리플레이할 투수: 탐지된 사례·놓친 사례를 정해진 수만큼 무작위로 고르고, 사례마다 가장 가까운 대조군을 붙인다."""
    picks = cfg["dashboard"]["replay"]
    hits = mt.window_results(windows, monitor, alarm="velo_alarm", index="velo_index")
    hits = hits[hits["group"] == "case"].set_index("case_id")["hit"]
    rng = np.random.default_rng(cfg["seed"])
    chosen = []
    for detected, count in ((True, picks["detected_cases"]), (False, picks["missed_cases"])):
        ids = hits.index[hits == detected].to_numpy()
        chosen += list(rng.choice(ids, min(count, len(ids)), replace=False))
    nearest = controls.sort_values(["case_id", "dist", "pitcher"]).groupby("case_id").head(picks["controls_per_case"])
    rows = []
    for case_id in chosen:
        c = cases[cases["case_id"] == case_id].iloc[0]
        rows.append({"pitcher": c["pitcher"], "season": c["season"], "role": c["role"], "group": "case", "case_id": case_id,
                     "part": c["part"], "il_date": c["il_date"], "detected": bool(hits[case_id])})
        for k in nearest[nearest["case_id"] == case_id].itertuples():
            rows.append({"pitcher": k.pitcher, "season": k.season, "role": k.role, "group": "control", "case_id": case_id,
                         "part": c["part"], "il_date": k.index_date, "detected": None})
    out = pd.DataFrame(rows)
    out["id"] = out["pitcher"].astype(str) + "_" + out["season"].astype(str)
    return out


def replay_file(entry, monitor: pd.DataFrame, outings: pd.DataFrame, windows: pd.DataFrame, names: pd.Series, rules: dict,
                core: list[str]) -> dict:
    mine = monitor[(monitor["pitcher"] == entry.pitcher) & (monitor["season"] == entry.season)].sort_values("game_date")
    mine_outings = outings[(outings["pitcher"] == entry.pitcher) & (outings["season"] == entry.season) & outings["eligible"]].sort_values("game_date")
    monitored = set(mine["game_pk"])
    by_game = mine.set_index("game_pk")
    rows = []
    for o in mine_outings.itertuples():
        row = {"date": o.game_date, "game_pk": o.game_pk, "n_fb": int(o.n_fb), "phase": "monitor" if o.game_pk in monitored else "baseline",
               **{f: r3(getattr(o, f)) for f in core}}
        if o.game_pk in monitored:
            m = by_game.loc[o.game_pk]
            row.update({"exp": {f: r3(m[f"expected_{f}"]) for f in core}, "sd": {f: r3(m[f"sd_{f}"]) for f in core},
                        "u": {f: r3(m[f"u_{f}"]) for f in core}, "t2": r3(m["t2"]),
                        "velo_index": r3(m["velo_index"]), "change_index": r3(m["change_index"]),
                        "velo_alarm": bool(m["velo_alarm"]), "change_alarm": bool(m["change_alarm"])})
        rows.append(row)
    velo, change = rules[entry.role]
    window_games = windows[(windows["case_id"] == entry.case_id) & (windows["pitcher"] == entry.pitcher)]["game_pk"].tolist()
    return {"id": entry.id, "name": names.get(entry.pitcher, str(entry.pitcher)), "season": int(entry.season), "role": entry.role,
            "group": entry.group, "case_id": int(entry.case_id), "part": entry.part, "il_date": entry.il_date,
            "detected": entry.detected, "window": window_games,
            "baseline_end": max((r["date"] for r in rows if r["phase"] == "baseline"), default=None),
            "limits": {"velo_k": r3(velo.k), "change_t2": r3(change.t2), "change_h": r3(change.h)}, "outings": rows}


def bullpen_file(replay: pd.DataFrame, monitor: pd.DataFrame, names: pd.Series) -> dict:
    load = pd.read_parquet(PROCESSED / "load.parquet")
    flags = [c for c in load.columns if c.startswith("flag_")]
    pitchers = []
    for e in replay[replay["role"] == "RP"].itertuples():
        mine = load[(load["pitcher"] == e.pitcher) & (load["season"] == e.season)].sort_values("game_date")
        alarms = monitor[(monitor["pitcher"] == e.pitcher) & (monitor["season"] == e.season) & (monitor["velo_alarm"] | monitor["change_alarm"])]
        pitchers.append({
            "id": e.id, "name": names.get(e.pitcher, str(e.pitcher)), "season": int(e.season), "group": e.group, "il_date": e.il_date,
            "days": [{"date": r.game_date, "pitches": int(r.n_all), "back_to_back": bool(r.back_to_back), "apps_3d": int(r.apps_3d),
                      "p7d": r3(r.p7d), "acwr": r3(r.acwr), "flags": [f[5:] for f in flags if getattr(r, f)]} for r in mine.itertuples()],
            "alarms": [{"date": r.game_date, "signals": [s for s in SIGNALS if getattr(r, f"{s}_alarm")]} for r in alarms.itertuples()]})
    return {"pitchers": pitchers, "flag_names": {"consecutive": "3일 연속 등판", "apps_3d": "3일 안 3회 등판", "p7d": "7일 투구 수 많음",
                                                  "acwr": "ACWR 초과", "long_short": "긴 등판 뒤 짧은 휴식"}}


def synthetic_highschool(cfg: dict) -> dict:
    """실제 고교 기록이 들어오기 전까지 쓰는 가상 데이터. 계산은 실제 모듈(src/common/highschool)과 같은 함수로 한다."""
    rules, rng = cfg["highschool"], np.random.default_rng(cfg["seed"])
    rows = []
    for s in range(1, rules["schools"] + 1):
        for day in pd.date_range("2026-03-21", "2026-08-30", freq="7D"):
            for game_day in ([day, day + pd.Timedelta(days=1)] if rng.random() < 0.35 else [day]):
                left, used = 27, rng.choice(8, size=rng.integers(2, 5), replace=False) + 1
                for i, p in enumerate(used):
                    outs = left if i == len(used) - 1 else int(rng.integers(1, max(2, left - (len(used) - i - 1))))
                    left -= outs
                    rows.append({"row": len(rows) + 2, "date": game_day, "competition": "주말리그", "game_no": 1, "school": f"S{s:02d}",
                                 "pitcher": f"S{s:02d}-P{p:02d}", "pitches": int(max(1, round(outs * rng.normal(5.2, 0.8)))), "outs": outs})
    frame = pd.DataFrame(rows)
    return highschool_payload(hs.daily_table(frame, rules), hs.violations(frame, hs.daily_table(frame, rules), rules), rules, synthetic=True)


def highschool_payload(daily: pd.DataFrame, violated: pd.DataFrame, rules: dict, synthetic: bool) -> dict:
    flag = rules["acwr"]["flag"]
    schools = []
    for school, d in daily.groupby("school"):
        pitchers = []
        for code, g in d.groupby("pitcher"):
            v = violated[violated["pitcher"] == code]
            kbsa = v[v["rule"].isin(hs.KBSA_RULES)]
            peak = g.loc[g["acwr_ok"], "acwr"].max()
            load_status = "경보" if g["acwr_flag"].any() else ("주의" if peak >= 1.0 else "보통") if np.isfinite(peak) else "계산 불가"
            pitchers.append({"code": code, "rule_status": "위반" if len(kbsa) else "준수", "load_status": load_status,
                             "violations": [{"date": r.date, "rule": r.rule, "detail": r.detail} for r in v.itertuples()],
                             "days": [{"date": r.date, "pitches": r3(r.pitches), "sum_3d": r3(r.sum_3d), "sum_7d": r3(r.sum_7d),
                                       "acwr": r3(r.acwr) if r.acwr_ok else None, "flag": bool(r.acwr_flag)}
                                      for r in g.itertuples() if r.pitches != 0 or r.acwr_flag]})
        schools.append({"code": school, "pitchers": pitchers})
    summary = hs.summary(daily, violated).to_dict("records")
    return {"synthetic": synthetic, "season": rules["season"], "acwr_flag": flag, "kbsa": rules["kbsa"],
            "foreign_rules": {k: v for k, v in rules["foreign_rules"].items() if v}, "schools": schools, "summary": summary}


def kbo_payload(cfg: dict) -> dict:
    """세 투수의 '신호 → 말소 → 결정' 날짜는 config 그대로(실제), 구속 EWMA는 수집 전이라 가상."""
    k = cfg["kbo_case"]
    rng = np.random.default_rng(cfg["seed"])
    pitchers = []
    for p in k["pitchers"]:
        removed = pd.Timestamp(p["removed"])
        dates = pd.date_range(removed - pd.Timedelta(days=5 * 12), removed - pd.Timedelta(days=5), freq="5D")
        velo = 150 + np.cumsum(rng.normal(0, 0.3, len(dates))) - np.linspace(0, 1.5, len(dates))
        z, series = 0.0, []
        for d, v in zip(dates, velo):
            z = 0.2 * (v - 150) / 0.7 + 0.8 * z
            series.append({"date": d, "velo": r3(v), "index": r3(-3 * z / 1.7)})
        pitchers.append({**p, "series": series})
    return {"synthetic": True, "pitchers": pitchers, "response_only": k["response_only"]}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "export_dashboard.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    core, seasons = cfg["features"]["core"], cfg["data"]["split"][SPLIT]
    OUT.mkdir(parents=True, exist_ok=True)
    monitor = pd.read_parquet(PROCESSED / f"monitor_{SPLIT}.parquet")
    alerts = pd.read_parquet(PROCESSED / f"alerts_{SPLIT}.parquet")
    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    cases = pd.read_csv(PROCESSED / "cases.csv", encoding="utf-8-sig", parse_dates=["il_date"])
    controls = pd.read_csv(PROCESSED / "controls.csv", encoding="utf-8-sig", parse_dates=["index_date"])
    windows = pd.read_csv(PROCESSED / "windows.csv", encoding="utf-8-sig")
    cases, controls, windows = (d[d["season"].isin(seasons)] for d in (cases, controls, windows))
    names = pd.read_parquet(ROOT / "data" / "raw" / "people.parquet").set_index("id")["full_name"]
    rules = cal.final_rules(cfg)

    sizes, synthetic = {}, []
    replay = pick_replay(cfg, monitor, cases, controls, windows)
    sizes["replay_index.json"] = dump("replay_index.json", [
        {"id": e.id, "name": names.get(e.pitcher, str(e.pitcher)), "season": int(e.season), "role": e.role, "group": e.group,
         "case_id": int(e.case_id), "part": e.part, "il_date": e.il_date, "detected": e.detected} for e in replay.itertuples()])
    for e in replay.itertuples():
        sizes[f"replay_{e.id}.json"] = dump(f"replay_{e.id}.json", replay_file(e, monitor, outings, windows, names, rules, core))
    keep = set(zip(replay["pitcher"], replay["season"]))
    mine = alerts[[(p, s) in keep for p, s in zip(alerts["pitcher"], alerts["season"])]]
    sizes["alerts.json"] = dump("alerts.json", [
        {"id": f"{a.pitcher}_{a.season}", "date": a.game_date, "signal": a.signal, "rule": a.rule, "index": r3(a.index), "card": a.card,
         **({"velo_mph": r3(a.velo_mph)} if a.signal == "velo_drop" else
            {"z": {f: r3(getattr(a, f"z_{f}")) for f in core}, "step": {f: r3(getattr(a, f"step_{f}")) for f in core},
             "zc": {f: r3(getattr(a, f"zc_{f}")) for f in core}})} for a in mine.itertuples()])
    performance = {"split": SPLIT, "seasons": seasons, "design_far": 100 / cfg["monitor"]["arl0_target"],
                   "results": pd.read_csv(TABLES / f"{SPLIT}_results.csv", encoding="utf-8-sig").round(3).to_dict("records"),
                   "opcurve": pd.read_csv(TABLES / f"{SPLIT}_opcurve.csv", encoding="utf-8-sig").round(3).to_dict("records"),
                   "tests": pd.read_csv(TABLES / f"{SPLIT}_tests.csv", encoding="utf-8-sig").round(4).to_dict("records")}
    sizes["performance.json"] = dump("performance.json", performance)
    sizes["bullpen.json"] = dump("bullpen.json", bullpen_file(replay, monitor, names))
    if (PROCESSED / "hs_daily.parquet").exists():
        daily = pd.read_parquet(PROCESSED / "hs_daily.parquet")
        violated = pd.read_csv(PROCESSED / "hs_violations.csv", encoding="utf-8-sig", parse_dates=["date"])
        sizes["highschool.json"] = dump("highschool.json", highschool_payload(daily, violated, cfg["highschool"], synthetic=False))
    else:
        sizes["highschool.json"] = dump("highschool.json", synthetic_highschool(cfg))
        synthetic.append("highschool.json")
    sizes["kbo_case.json"] = dump("kbo_case.json", kbo_payload(cfg))
    synthetic.append("kbo_case.json")

    version = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    meta = {"as_of": outings["game_date"].max(), "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "version": version,
            "split": SPLIT, "seasons": seasons, "synthetic": synthetic, "signals": SIGNALS,
            "config_sha256": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in ("config.yaml", "config_calibrated.yaml")},
            "sources": "MLB Statcast(Baseball Savant), MLB Stats API; 고교·KBO는 가상 데이터 표시 참고"}
    sizes["meta.json"] = dump("meta.json", meta)

    biggest = max(v for k, v in sizes.items() if k.startswith("replay_"))
    log.info("JSON %d개 → %s. 리플레이 투수 %d명, 가장 큰 리플레이 파일 %.0f KB, 가상 데이터: %s", len(sizes), OUT, len(replay), biggest / 1024, synthetic)
    for name, size in sorted(sizes.items(), key=lambda kv: -kv[1])[:8]:
        print(f"{name:32s} {size / 1024:7.1f} KB")
    print("나머지 리플레이 파일은 모두", f"{biggest / 1024:.0f} KB 이하")


if __name__ == "__main__":
    main()
