"""영입 전 점검 (화면 5): 2026 KBO 외국인 투수의 MLB·트리플A 기록에 같은 감시 엔진을 돌려 대시보드 JSON으로 내보낸다.

- 대상 목록: config_scout.yaml (평가 설정 파일과 분리. config.yaml 해시를 바꾸지 않기 위해)
- 트리플A 투구: Baseball Savant 'Minor League Statcast'(minors=true) CSV를 선수별로 받아 data/raw/aaa/<mlbam>.parquet에 저장(있으면 재사용)
- 등판 표·감시: src/common의 outings·pipeline·myt를 MLB와 똑같이 적용. 단, 트리플A는 구장 자료가 없어 구장 보정을 하지 않고
  한계값은 MLB 개발셋 값을 그대로 쓴다 — 화면에 '참고용'으로 표시한다.
- MLB 시즌: 이미 있는 monitor_dev/val/sealed.parquet와 outings.parquet에서 가져온다.
- 출력: dashboard-web/public/data/scout.json, replay/aaa_<mlbam>_<season>.json, pitchers.json·alerts.json에 트리플A 항목 추가

    python -m src.16_scout            # 13_export_dashboard 뒤에 실행
    python -m src.16_scout --no-download   # 받아 둔 트리플A 자료만 쓴다
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import time

import numpy as np
import pandas as pd
import requests
import yaml

from src.common import baseline_window as bw
from src.common import calibration as cal
from src.common import myt
from src.common import outings as og
from src.common import pipeline
from src.common import scout
from src.common.config import ROOT, load_config

RAW_AAA = ROOT / "data" / "raw" / "aaa"
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "dashboard-web" / "public" / "data"
SAVANT = "https://baseballsavant.mlb.com/statcast_search/csv"
COLUMNS = ["game_pk", "game_date", "pitcher", "p_throws", "inning", "inning_topbot", "at_bat_number", "pitch_number",
           "pitch_type", "description", "events", "plate_z", "sz_top", "sz_bot", "zone", *og.FEATURE_COLUMNS.values()]
log = logging.getLogger("pitchsignal.scout")


def download_aaa(mlbam: int, seasons: list[int], session: requests.Session) -> pd.DataFrame:
    """한 투수의 트리플A 정규시즌 투구 전부 (여러 시즌을 한 번에)."""
    params = {"all": "true", "hfGT": "R|", "hfSea": "|".join(str(s) for s in seasons) + "|", "player_type": "pitcher",
              "pitchers_lookup[]": str(mlbam), "min_pitches": "0", "min_results": "0", "group_by": "name", "sort_col": "pitches",
              "player_event_sort": "api_p_release_speed", "sort_order": "desc", "min_pas": "0", "type": "details", "minors": "true"}
    r = session.get(SAVANT, params=params, timeout=180)
    r.raise_for_status()
    if not r.text.strip():
        return pd.DataFrame()
    df = pd.read_csv(io.StringIO(r.text), low_memory=False)
    df["game_date"] = pd.to_datetime(df["game_date"])
    return df


def aaa_pitches(cfg_scout: dict, download: bool) -> pd.DataFrame:
    RAW_AAA.mkdir(parents=True, exist_ok=True)
    parts, session = [], requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (PitchSignal research; contact robin1967@unist.ac.kr)"
    for p in cfg_scout["pitchers"]:
        if p["mlbam"] is None:
            continue
        path = RAW_AAA / f"{p['mlbam']}.parquet"
        if path.exists():
            df = pd.read_parquet(path)
        elif download:
            df = download_aaa(p["mlbam"], cfg_scout["aaa_seasons"], session)
            df.to_parquet(path, compression="zstd", index=False)
            log.info("트리플A 받음: %s (%d) 투구 %d, 경기 %d", p["name"], p["mlbam"], len(df), df["game_pk"].nunique() if len(df) else 0)
            time.sleep(1.5)
        else:
            continue
        if len(df):
            parts.append(df)
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def aaa_tables(cfg: dict, pitches: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """트리플A 투구 → 등판 표(구장 보정 없음), 감시 표, 경보 카드."""
    outings, fbs = [], []
    for season, chunk in pitches.groupby(pitches["game_date"].dt.year):
        o, fb = og.build_outings(chunk[COLUMNS].copy(), int(season), cfg["features"])
        outings.append(o); fbs.append(fb)
    outings, pitches_fb = pd.concat(outings, ignore_index=True), pd.concat(fbs, ignore_index=True)
    for f in cfg["features"]["park_adjust"]["features"]:
        outings[f"park_{f}"] = 0.0                                 # 구장 보정 없음 (트리플A 구장 자료가 없음)
    table = pipeline.monitor_table(cfg, outings, pitches_fb)
    core = cfg["features"]["core"]
    alerts = myt.build_alerts(table, outings[[*myt.OUTING, *core]], core, cal.final_rules(cfg)) if len(table) else pd.DataFrame()
    return outings, table, alerts


def mlb_tables(cfg: dict, ids: list[int]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """대상 투수들의 MLB 등판·감시·경보 (평가 때 저장한 표에서)."""
    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    outings = outings[outings["pitcher"].isin(ids)]
    tables, alerts = [], []
    for split in ("dev", "val", "sealed"):
        if (PROCESSED / f"monitor_{split}.parquet").exists():
            t = pd.read_parquet(PROCESSED / f"monitor_{split}.parquet"); tables.append(t[t["pitcher"].isin(ids)])
            a = pd.read_parquet(PROCESSED / f"alerts_{split}.parquet"); alerts.append(a[a["pitcher"].isin(ids)])
    return outings, pd.concat(tables, ignore_index=True), pd.concat(alerts, ignore_index=True)


def joined(outings: pd.DataFrame, table: pd.DataFrame, cfg: dict, league: str) -> pd.DataFrame:
    """적격 등판에 감시 표를 붙인 긴 표 (phase, 지수, 경보 포함)."""
    o = outings[outings["eligible"]].copy()
    o["phase"] = bw.phase(o, cfg["baseline"]).to_numpy()
    o = o[o["phase"] != ""]
    cols = ["pitcher", "season", "game_pk", "velo_index", "change_index", "velo_alarm", "change_alarm", "uv",
            *[f"expected_{f}" for f in cfg["features"]["core"]], *[f"sd_{f}" for f in cfg["features"]["core"]], *[f"u_{f}" for f in cfg["features"]["core"]]]
    out = o.merge(table[cols], on=["pitcher", "season", "game_pk"], how="left")
    for c in ("velo_alarm", "change_alarm"):
        out[c] = out[c].map(lambda v: bool(v) if v == v and v is not None else False)   # 시작 구간(감시 표에 없음)은 False
    out["league"] = league
    return out


def replay_payload(group: pd.DataFrame, name: str, rules: dict, core: list[str], league: str) -> dict:
    """리플레이 파일 (13_export_dashboard.replay_file과 같은 모양). 트리플A는 IL·관찰 창이 없다."""
    g = group.sort_values("game_date")
    rows = []
    for o in g.itertuples():
        row = {"date": o.game_date, "game_pk": int(o.game_pk), "n_fb": int(o.n_fb), "n_all": int(o.n_all), "fb": o.primary_fb, "phase": o.phase,
               **{f: _r3(getattr(o, f)) for f in core}}
        if o.phase == "monitor" and not pd.isna(o.velo_index):
            row.update({"exp": {f: _r3(getattr(o, f"expected_{f}")) for f in core}, "sd": {f: _r3(getattr(o, f"sd_{f}")) for f in core},
                        "u": {f: round(float(getattr(o, f"u_{f}")), 4) for f in core}, "uv": round(float(o.uv), 4),
                        "velo_index": _r3(o.velo_index), "change_index": _r3(o.change_index), "velo_alarm": bool(o.velo_alarm), "change_alarm": bool(o.change_alarm)})
        rows.append(row)
    role = g["role"].iloc[0]
    velo, change = rules[role]
    return {"id": f"aaa_{int(g['pitcher'].iloc[0])}_{int(g['season'].iloc[0])}", "name": name, "season": int(g["season"].iloc[0]), "role": role, "league": league,
            "group": "other", "case_id": None, "part": None, "il_date": None, "detected": None, "window": [],
            "baseline_end": max((r["date"] for r in rows if r["phase"] == "baseline"), default=None),
            "limits": {"velo_k": round(float(velo.k), 4), "change_t2": round(float(change.t2), 4), "change_h": round(float(change.h), 4), "lam": velo.lam}, "outings": rows}


def _r3(x):
    return None if x is None or (isinstance(x, float) and np.isnan(x)) else round(float(x), 3)


def _dump(name: str, payload) -> None:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=_default, allow_nan=False), encoding="utf-8")


def _default(v):
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else round(float(v), 4)
    if isinstance(v, np.bool_):
        return bool(v)
    raise TypeError(str(type(v)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-download", action="store_true")
    a = ap.parse_args()
    (ROOT / "reports" / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "scout.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    cfg_scout = yaml.safe_load((ROOT / "config_scout.yaml").read_text(encoding="utf-8"))["scout"]
    core, rules = cfg["features"]["core"], cal.final_rules(cfg)
    labels = pd.read_csv(PROCESSED / "labels.csv", encoding="utf-8-sig", parse_dates=["il_date"])
    ids = [p["mlbam"] for p in cfg_scout["pitchers"] if p["mlbam"] is not None]

    pitches = aaa_pitches(cfg_scout, download=not a.no_download)
    if len(pitches):
        aaa_out, aaa_tab, aaa_alerts = aaa_tables(cfg, pitches)
        aaa_long = joined(aaa_out, aaa_tab, cfg, "AAA")
    else:
        aaa_out = aaa_tab = aaa_alerts = aaa_long = pd.DataFrame()
    mlb_out, mlb_tab, mlb_alerts = mlb_tables(cfg, ids)
    mlb_long = joined(mlb_out, mlb_tab, cfg, "MLB")
    everything = pd.concat([mlb_long, aaa_long], ignore_index=True) if len(aaa_long) else mlb_long

    pitchers_out, aaa_catalog, aaa_alert_rows = [], [], []
    for p in cfg_scout["pitchers"]:
        entry = {**p, "seasons": [], "timeline": [], "il": []}
        if p["mlbam"] is not None:
            mine = everything[everything["pitcher"] == p["mlbam"]]
            for (season, league), g in mine.groupby(["season", "league"]):
                monitored = g["phase"].eq("monitor").sum()
                summary = scout.nan_to_none(scout.season_summary(g))
                il = scout.arm_il(labels, p["mlbam"], int(season)) if league == "MLB" else None
                replay_id = f"{p['mlbam']}_{season}" if league == "MLB" else f"aaa_{p['mlbam']}_{season}"
                has_replay = (OUT / "replay" / f"{replay_id}.json").exists() if league == "MLB" else monitored > 0
                entry["seasons"].append({"season": int(season), **summary, "il": il, "replay": replay_id if has_replay else None})
                if il:
                    entry["il"].append({"season": int(season), **il})
                if league == "AAA" and monitored > 0:
                    payload = replay_payload(g, p["name"], rules, core, "AAA")
                    _dump(f"replay/{replay_id}.json", payload)
                    aaa_catalog.append({"id": replay_id, "name": p["name"], "season": int(season), "role": summary["role"], "group": "other", "case_id": None,
                                        "part": None, "il_date": None, "detected": None, "n_mon": int(monitored), "alarms_velo": summary["alarms_velo"],
                                        "alarms_change": summary["alarms_change"], "split": "aaa", "league": "AAA"})
            entry["timeline"] = scout.timeline(mine)
            entry["seasons"].sort(key=lambda s: (s["season"], s["league"]))
        pitchers_out.append(entry)
    if len(aaa_alerts):
        for al in aaa_alerts.itertuples():
            aaa_alert_rows.append({"id": f"aaa_{al.pitcher}_{al.season}", "date": al.game_date, "signal": al.signal, "rule": al.rule, "index": _r3(al.index), "card": al.card,
                                   **({"velo_mph": _r3(al.velo_mph)} if al.signal == "velo_drop" else
                                      {"z": {f: _r3(getattr(al, f"z_{f}")) for f in core}, "step": {f: _r3(getattr(al, f"step_{f}")) for f in core},
                                       "zc": {f: _r3(getattr(al, f"zc_{f}")) for f in core}})})

    _dump("scout.json", {"season": 2026, "as_of_note": "트리플A 기록은 구장 보정 없이, 한계값은 MLB 개발셋 값을 그대로 써서 참고용", "aaa_seasons": cfg_scout["aaa_seasons"],
                         "pitchers": pitchers_out})
    # 검색 목록·경보 카드에 트리플A 항목을 더한다 (13_export가 만든 파일에 덧붙임, 같은 id는 교체)
    idx_path, alerts_path = OUT / "pitchers.json", OUT / "alerts.json"
    idx = [x for x in json.loads(idx_path.read_text(encoding="utf-8")) if not str(x["id"]).startswith("aaa_")] + aaa_catalog
    _dump("pitchers.json", idx)
    alerts = [x for x in json.loads(alerts_path.read_text(encoding="utf-8")) if not str(x["id"]).startswith("aaa_")] + aaa_alert_rows
    _dump("alerts.json", alerts)
    log.info("영입 전 점검: 투수 %d명(기록 있는 %d명), 트리플A 투수-시즌 %d개, 트리플A 경보 %d건, 검색 목록 %d개",
             len(pitchers_out), sum(1 for e in pitchers_out if e["seasons"]), len(aaa_catalog), len(aaa_alert_rows), len(idx))


if __name__ == "__main__":
    main()
