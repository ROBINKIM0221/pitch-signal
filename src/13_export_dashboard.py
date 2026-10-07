"""대시보드용 JSON 내보내기 (단계 8.1). 파일 표는 docs/SPEC.md 3.17절 표 15.

검증셋(monitor_val.parquet, alerts_val.parquet)에서 감시 등판이 있는 모든 투수-시즌의 리플레이(data/replay/*.json)와 검색 목록(pitchers.json),
경보 카드·성능 비교·불펜 부하를 만들고, 아직 결과가 없는 고교·KBO는
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
from src.common import tournament as tn
from src.common.config import ROOT, load_config

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
OUT = ROOT / "dashboard-web" / "public" / "data"
SPLIT = "val"
SIGNALS = {"velo": "구속 하락 신호", "change": "폼 변화 신호"}
log = logging.getLogger("pitchsignal.export")


def dump(name: str, payload) -> int:
    """JSON으로 저장한다. 표준 JSON에는 NaN이 없으므로 결측은 null로 바꾼다 (브라우저의 JSON.parse가 NaN을 거부함)."""
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_json_default, allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return path.stat().st_size


def records(frame: pd.DataFrame, digits: int) -> list[dict]:
    """표를 레코드 목록으로. 결측은 None."""
    rounded = frame.round(digits)
    return rounded.astype(object).where(pd.notna(rounded), None).to_dict("records")


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


def opt(x):
    """표에서 꺼낸 값의 결측(NaN·NaT·None)은 None으로, 정수형 실수는 int로."""
    if x is None or (isinstance(x, float) and np.isnan(x)) or x is pd.NaT:
        return None
    if isinstance(x, (np.floating, float)) and float(x).is_integer():
        return int(x)
    return x


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
        row = {"date": o.game_date, "game_pk": o.game_pk, "n_fb": int(o.n_fb), "n_all": int(o.n_all), "fb": o.primary_fb,
               "phase": "monitor" if o.game_pk in monitored else "baseline", **{f: r3(getattr(o, f)) for f in core}}
        if o.game_pk in monitored:
            m = by_game.loc[o.game_pk]
            # u(세 특징의 표준화 예측 오차)와 uv(구속 하나로 돌린 표준화 오차)는 화면에서 한계 배수를 바꿔 다시 계산할 때 쓴다
            row.update({"exp": {f: r3(m[f"expected_{f}"]) for f in core}, "sd": {f: r3(m[f"sd_{f}"]) for f in core},
                        "u": {f: round(float(m[f"u_{f}"]), 4) for f in core}, "uv": round(float(m["uv"]), 4),
                        "velo_index": r3(m["velo_index"]), "change_index": r3(m["change_index"]),
                        "velo_alarm": bool(m["velo_alarm"]), "change_alarm": bool(m["change_alarm"])})
        rows.append(row)
    velo, change = rules[entry.role]
    has_case = opt(entry.case_id) is not None
    window_games = windows[(windows["case_id"] == entry.case_id) & (windows["pitcher"] == entry.pitcher)]["game_pk"].tolist() if has_case else []
    return {"id": entry.id, "name": names.get(entry.pitcher, str(entry.pitcher)), "season": int(entry.season), "role": entry.role,
            "group": entry.group, "case_id": int(entry.case_id) if has_case else None, "part": opt(entry.part), "il_date": opt(entry.il_date),
            "detected": opt(entry.detected), "window": window_games,
            "baseline_end": max((r["date"] for r in rows if r["phase"] == "baseline"), default=None),
            "limits": {"velo_k": round(float(velo.k), 4), "change_t2": round(float(change.t2), 4), "change_h": round(float(change.h), 4), "lam": velo.lam}, "outings": rows}


def catalog(monitor: pd.DataFrame, cases: pd.DataFrame, controls: pd.DataFrame, windows: pd.DataFrame, labels: pd.DataFrame, split: str) -> pd.DataFrame:
    """검색용 전체 목록: 한 분할(dev/val)에서 감시 등판이 있는 모든 투수-시즌. 사례·대조군이면 그 역할을, 아니면 'other'를 적는다.
    사례가 아닌데 팔 부상 IL이 있던 투수-시즌(사례 기준 미충족)은 그 첫 IL 날짜만 표시용으로 남긴다."""
    hits = mt.window_results(windows, monitor, alarm="velo_alarm", index="velo_index")
    hits = hits[hits["group"] == "case"].set_index("case_id")["hit"]
    first_case = cases.sort_values("il_date").drop_duplicates(["pitcher", "season"]).set_index(["pitcher", "season"])
    first_control = controls.sort_values(["dist", "case_id"]).drop_duplicates(["pitcher", "season"]).set_index(["pitcher", "season"])
    arm_il = labels[labels["part"].isin(["elbow", "shoulder"])].sort_values("il_date").drop_duplicates(["pitcher", "season"]).set_index(["pitcher", "season"])
    counts = monitor.groupby(["pitcher", "season"]).agg(role=("role", "first"), n_mon=("game_pk", "size"),
                                                         alarms_velo=("velo_alarm", "sum"), alarms_change=("change_alarm", "sum"))
    rows = []
    for (pitcher, season), c in counts.iterrows():
        key = (pitcher, season)
        if key in first_case.index:
            k = first_case.loc[key]
            row = {"group": "case", "case_id": int(k["case_id"]), "part": k["part"], "il_date": k["il_date"], "detected": bool(hits.get(k["case_id"], False))}
        elif key in first_control.index:
            k = first_control.loc[key]; part = cases.set_index("case_id").loc[k["case_id"], "part"]
            row = {"group": "control", "case_id": int(k["case_id"]), "part": part, "il_date": k["index_date"], "detected": None}
        else:
            il = arm_il.loc[key] if key in arm_il.index else None
            row = {"group": "other", "case_id": None, "part": il["part"] if il is not None else None,
                   "il_date": il["il_date"] if il is not None else None, "detected": None}
        rows.append({"pitcher": pitcher, "season": int(season), "role": c["role"], "n_mon": int(c["n_mon"]),
                     "alarms_velo": int(c["alarms_velo"]), "alarms_change": int(c["alarms_change"]), **row})
    out = pd.DataFrame(rows)
    out["id"] = out["pitcher"].astype(str) + "_" + out["season"].astype(str)
    out["split"] = split
    return out


def bullpen_file(replay: pd.DataFrame, monitor: pd.DataFrame, names: pd.Series, acwr_flag: float) -> dict:
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
    return {"pitchers": pitchers, "acwr_flag": acwr_flag,
            "flag_names": {"consecutive": "3일 연속 등판", "apps_3d": "3일 안 3회 등판", "p7d": "7일 투구 수 많음",
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
    summary = records(hs.summary(daily, violated), 3)
    return {"synthetic": synthetic, "season": rules["season"], "acwr_flag": flag, "kbsa": rules["kbsa"],
            "foreign_rules": {k: v for k, v in rules["foreign_rules"].items() if v}, "schools": schools, "summary": summary}


def kbo_payload(cfg: dict) -> dict:
    """세 투수의 '신호 → 말소 → 결정' 날짜(config, 공개 기록). 구속 그래프는 화면에서 직접 입력한 자료로 그린다 (가상 자료 없음)."""
    k = cfg["kbo_case"]
    return {"synthetic": False, "pitchers": list(k["pitchers"]), "response_only": k["response_only"]}


def watchlist(cfg: dict, sealed_catalog: pd.DataFrame, names: pd.Series, outings: pd.DataFrame, labels: pd.DataFrame) -> dict:
    """2026 시즌 감시 현황: 최근 N주(기본 4주) 안에 경보가 울린 투수-시즌과 그 뒤 팔 부상 IL 여부. 운영 화면 '이번 주 점검 대상'의 실제 자료판."""
    mon = pd.read_parquet(PROCESSED / "monitor_sealed.parquet")
    as_of = pd.Timestamp(outings["game_date"].max())
    since = as_of - pd.Timedelta(weeks=4)
    arm = labels[labels["part"].isin(["elbow", "shoulder"]) & labels["season"].isin(cfg["data"]["split"]["sealed"])]
    rows = []
    for (pitcher, season), g in mon.sort_values("game_date").groupby(["pitcher", "season"]):
        recent = g[(g["game_date"] >= since) & (g["velo_alarm"] | g["change_alarm"])]
        if recent.empty:
            continue
        last = g.iloc[-1]
        il_after = arm[(arm["pitcher"] == pitcher) & (arm["il_date"] > recent["game_date"].min())]["il_date"].min()
        rows.append({"id": f"{pitcher}_{season}", "name": names.get(pitcher, str(pitcher)), "role": last["role"],
                     "alarm_dates": [d.strftime("%Y-%m-%d") for d in recent["game_date"]],
                     "signals": sorted({s for s, flag in (("velo", recent["velo_alarm"].any()), ("change", recent["change_alarm"].any())) if flag}),
                     "last_outing": last["game_date"], "velo_index": r3(last["velo_index"]), "change_index": r3(last["change_index"]),
                     "il_after": None if pd.isna(il_after) else il_after.strftime("%Y-%m-%d"),
                     "n_mon": int(len(g)), "alarms_velo": int(g["velo_alarm"].sum()), "alarms_change": int(g["change_alarm"].sum())})
    rows.sort(key=lambda r: (r["alarm_dates"][-1], r["name"]), reverse=True)
    season_alarms = {"velo": int(mon["velo_alarm"].sum()), "change": int(mon["change_alarm"].sum()), "pitcher_seasons": int(mon.groupby(["pitcher", "season"]).ngroups),
                     "outings": int(len(mon))}
    return {"as_of": as_of.strftime("%Y-%m-%d"), "since": since.strftime("%Y-%m-%d"), "weeks": 4, "season": cfg["data"]["split"]["sealed"][0],
            "rows": rows, "season_totals": season_alarms}


def engine_params(cfg: dict) -> dict:
    """브라우저용 간이 엔진(구속 하나)이 빌려 쓰는 값: 역할별 투구별 흔들림 σ_w(mph), 평소가 움직이는 크기 Q·등판 흔들림 Σ_e(단위 없앤 값),
    λ, 실측 한계 k, 시작 구간 규칙. 모두 MLB 개발셋에서 추정·보정한 값이다."""
    n_min = pd.read_csv(TABLES / "n_min.csv", encoding="utf-8-sig")
    dyn, final = cfg["baseline"]["dynamics"], cfg["monitor"]["final"]
    v = dyn["features"].index("velo")
    roles = {}
    for role in ("SP", "RP"):
        sigma_w = float(n_min[(n_min["group"] == role) & (n_min["feature"] == "velo")]["sigma_w"].iloc[0])
        roles[role] = {"sigma_w": round(sigma_w, 4), "q": dyn[role]["Q"][v][v], "se": dyn[role]["Se"][v][v],
                       "lam": final["lam"], "k": final["velo"][role]["k"]}
    rules = {key: cfg["baseline"][key] for key in ("starter_outings", "reliever_outings", "reliever_min_fastballs")}
    return {"roles": roles, "rules": rules, "source": "MLB 개발셋 2021~2023 (config_calibrated.yaml, reports/tables/n_min.csv)"}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "export_dashboard.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    core, seasons = cfg["features"]["core"], cfg["data"]["split"][SPLIT]
    OUT.mkdir(parents=True, exist_ok=True)
    monitor = pd.read_parquet(PROCESSED / f"monitor_{SPLIT}.parquet")
    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    cases = pd.read_csv(PROCESSED / "cases.csv", encoding="utf-8-sig", parse_dates=["il_date"])
    controls = pd.read_csv(PROCESSED / "controls.csv", encoding="utf-8-sig", parse_dates=["index_date"])
    windows = pd.read_csv(PROCESSED / "windows.csv", encoding="utf-8-sig")
    cases, controls, windows = (d[d["season"].isin(seasons)] for d in (cases, controls, windows))
    names = pd.read_parquet(ROOT / "data" / "raw" / "people.parquet").set_index("id")["full_name"]
    rules = cal.final_rules(cfg)

    sizes, synthetic = {}, []
    labels = pd.read_csv(PROCESSED / "labels.csv", encoding="utf-8-sig", parse_dates=["il_date"])
    all_cases = pd.read_csv(PROCESSED / "cases.csv", encoding="utf-8-sig", parse_dates=["il_date"])
    all_controls = pd.read_csv(PROCESSED / "controls.csv", encoding="utf-8-sig", parse_dates=["index_date"])
    all_windows = pd.read_csv(PROCESSED / "windows.csv", encoding="utf-8-sig")
    # 검색·리플레이는 개발셋(2021~2023)과 검증셋(2024~2025)을 모두 내보낸다. 봉인 시즌(2026)은 내보내지 않는다.
    catalogs, alert_rows = [], []
    splits = ["dev", "val"] + (["sealed"] if (PROCESSED / "monitor_sealed.parquet").exists() else [])   # 봉인 시즌은 봉인 평가(09) 뒤에만
    for split in splits:
        split_seasons = cfg["data"]["split"][split]
        mon = pd.read_parquet(PROCESSED / f"monitor_{split}.parquet")
        al = pd.read_parquet(PROCESSED / f"alerts_{split}.parquet")
        sel = lambda d: d[d["season"].isin(split_seasons)]  # noqa: E731
        part = catalog(mon, sel(all_cases), sel(all_controls), sel(all_windows), sel(labels), split)
        catalogs.append(part)
        for e in part.itertuples():
            sizes[f"replay/{e.id}.json"] = dump(f"replay/{e.id}.json", replay_file(e, mon, outings, sel(all_windows), names, rules, core))
        alert_rows += [
            {"id": f"{a.pitcher}_{a.season}", "date": a.game_date, "signal": a.signal, "rule": a.rule, "index": r3(a.index), "card": a.card,
             **({"velo_mph": r3(a.velo_mph)} if a.signal == "velo_drop" else
                {"z": {f: r3(getattr(a, f"z_{f}")) for f in core}, "step": {f: r3(getattr(a, f"step_{f}")) for f in core},
                 "zc": {f: r3(getattr(a, f"zc_{f}")) for f in core}})} for a in al.itertuples()]
    everyone = pd.concat(catalogs, ignore_index=True)
    sizes["pitchers.json"] = dump("pitchers.json", [
        {"id": e.id, "name": names.get(e.pitcher, str(e.pitcher)), "season": e.season, "role": e.role, "group": e.group, "case_id": opt(e.case_id),
         "part": opt(e.part), "il_date": opt(e.il_date), "detected": opt(e.detected), "n_mon": e.n_mon, "alarms_velo": e.alarms_velo,
         "alarms_change": e.alarms_change, "split": e.split} for e in everyone.itertuples()])
    sizes["alerts.json"] = dump("alerts.json", alert_rows)
    replay = pick_replay(cfg, monitor, cases, controls, windows)                       # 불펜 부하 화면의 표본
    performance = {"split": SPLIT, "seasons": seasons, "design_far": 100 / cfg["monitor"]["arl0_target"],
                   "results": records(pd.read_csv(TABLES / f"{SPLIT}_results.csv", encoding="utf-8-sig"), 3),
                   "opcurve": records(pd.read_csv(TABLES / f"{SPLIT}_opcurve.csv", encoding="utf-8-sig"), 3),
                   "tests": records(pd.read_csv(TABLES / f"{SPLIT}_tests.csv", encoding="utf-8-sig"), 4)}
    sealed_dir = ROOT / "reports" / "sealed"
    if (sealed_dir / "sealed_results.csv").exists():
        performance["sealed"] = {"seasons": cfg["data"]["split"]["sealed"],
                                 "results": records(pd.read_csv(sealed_dir / "sealed_results.csv", encoding="utf-8-sig"), 3),
                                 "opcurve": records(pd.read_csv(sealed_dir / "sealed_opcurve.csv", encoding="utf-8-sig"), 3),
                                 "tests": records(pd.read_csv(sealed_dir / "sealed_tests.csv", encoding="utf-8-sig"), 4),
                                 "run_info": (sealed_dir / "run_info.txt").read_text(encoding="utf-8")}
    if (TABLES / "alarm_followup.csv").exists():
        performance["followup"] = records(pd.read_csv(TABLES / "alarm_followup.csv", encoding="utf-8-sig"), 4)
    sizes["performance.json"] = dump("performance.json", performance)
    if "sealed" in splits:
        sizes["watchlist.json"] = dump("watchlist.json", watchlist(cfg, everyone[everyone["split"] == "sealed"], names, outings, labels))
    sizes["bullpen.json"] = dump("bullpen.json", bullpen_file(replay, monitor, names, cfg["load"]["acwr_flag"]))
    if (PROCESSED / "hs_tournament_rows.parquet").exists():                                   # 2025 전국체전 실제 기록 (src/17)
        info, hs_rules = tn.tournament_config()
        sizes["highschool.json"] = dump("highschool.json", tn.payload(
            pd.read_parquet(PROCESSED / "hs_tournament_rows.parquet"), pd.read_parquet(PROCESSED / "hs_tournament_daily.parquet"),
            pd.read_csv(PROCESSED / "hs_tournament_violations.csv", encoding="utf-8-sig", parse_dates=["date"]), hs_rules, info))
    elif (PROCESSED / "hs_daily.parquet").exists():
        daily = pd.read_parquet(PROCESSED / "hs_daily.parquet")
        violated = pd.read_csv(PROCESSED / "hs_violations.csv", encoding="utf-8-sig", parse_dates=["date"])
        sizes["highschool.json"] = dump("highschool.json", highschool_payload(daily, violated, cfg["highschool"], synthetic=False))
    else:
        sizes["highschool.json"] = dump("highschool.json", synthetic_highschool(cfg))
        synthetic.append("highschool.json")
    sizes["kbo_case.json"] = dump("kbo_case.json", kbo_payload(cfg))
    sizes["engine_params.json"] = dump("engine_params.json", engine_params(cfg))

    version = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    meta = {"as_of": outings["game_date"].max(), "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "version": version,
            "split": SPLIT, "seasons": seasons, "dev_seasons": cfg["data"]["split"]["dev"], "sealed_seasons": cfg["data"]["split"]["sealed"] if "sealed" in splits else None,
            "synthetic": synthetic, "signals": SIGNALS,
            "config_sha256": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in ("config.yaml", "config_calibrated.yaml")},
            "sources": "MLB Statcast(Baseball Savant), MLB Stats API, KBSA 기록실(전국체전); 가상 데이터는 synthetic 목록 참고"}
    sizes["meta.json"] = dump("meta.json", meta)

    replays = {k: v for k, v in sizes.items() if k.startswith("replay/")}
    log.info("JSON %d개 → %s. 검색 가능한 투수-시즌 %d개(리플레이 합계 %.1f MB, 가장 큰 파일 %.0f KB), 가상 데이터: %s",
             len(sizes), OUT, len(everyone), sum(replays.values()) / 1e6, max(replays.values()) / 1024, synthetic)
    for name, size in sorted(((k, v) for k, v in sizes.items() if not k.startswith("replay/")), key=lambda kv: -kv[1])[:8]:
        print(f"{name:32s} {size / 1024:7.1f} KB")
    print(f"리플레이 파일 {len(replays)}개, 합계 {sum(replays.values()) / 1e6:.1f} MB, 가장 큰 파일 {max(replays.values()) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
