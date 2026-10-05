"""등판 표 만들기 (단계 2.3). 규칙은 docs/SPEC.md 3.2·3.4·3.5절.

내려받은 Statcast를 시즌별로 읽어
  data/processed/outings.parquet      투수 × 경기 한 줄 (역할, 주력 패스트볼, 투구 수, 특징 F1~F9, 피안타·볼넷·아웃)
  data/processed/pitches_fb.parquet   핵심 특징에 결측이 없는 주력 패스트볼 투구별 특징
을 만든다. 성능 지표는 계산하지 않는다.

사용 예:
    python -m src.03_outings
"""
from __future__ import annotations

import logging

import pandas as pd

from src.common import outings as og
from src.common import statcast as st
from src.common.config import ROOT, load_config

RAW = ROOT / "data" / "raw" / "statcast"
PROCESSED = ROOT / "data" / "processed"
COLUMNS = ["game_pk", "game_date", "pitcher", "p_throws", "inning", "inning_topbot", "at_bat_number", "pitch_number",
           "pitch_type", "description", "events", "plate_z", "sz_top", "sz_bot", "zone", *og.FEATURE_COLUMNS.values()]
log = logging.getLogger("pitchsignal.outings")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "outings.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    outings, pitches_fb = [], []
    for season in cfg["data"]["seasons"]:
        o, f = og.build_outings(st.load_season(RAW, season, COLUMNS), season, cfg["features"])
        log.info("%d 시즌: 등판 %d, 적격 등판 %d, 주력 패스트볼 투구 %d", season, len(o), int(o["eligible"].sum()), len(f))
        outings.append(o)
        pitches_fb.append(f)
    outings, pitches_fb = pd.concat(outings, ignore_index=True), pd.concat(pitches_fb, ignore_index=True)
    outings.to_parquet(PROCESSED / "outings.parquet", compression="zstd", index=False)
    pitches_fb.to_parquet(PROCESSED / "pitches_fb.parquet", compression="zstd", index=False)

    pitchers = outings.drop_duplicates(["season", "pitcher"])
    summary = pd.DataFrame({
        "outings": outings.groupby("season").size(),
        "eligible": outings.groupby("season")["eligible"].sum(),
        "starts": outings.groupby("season")["is_start"].sum(),
        "SP": pitchers[pitchers["role"] == "SP"].groupby("season").size(),
        "RP": pitchers[pitchers["role"] == "RP"].groupby("season").size(),
        **{f"primary_{t}": pitchers[pitchers["primary_fb"] == t].groupby("season").size()
           for t in cfg["features"]["primary_fastball_types"]},
        "no_primary": pitchers[pitchers["primary_fb"].isna()].groupby("season").size(),
        "core_missing_mean": outings.groupby("season")["core_missing_frac"].mean(),
        "core_missing_p95": outings.groupby("season")["core_missing_frac"].quantile(0.95),
    }).fillna(0)
    summary.to_csv(ROOT / "reports" / "tables" / "outings_summary.csv", encoding="utf-8-sig")
    print(summary.T.to_string(float_format=lambda v: f"{v:.3f}" if v < 1 else f"{v:.0f}"))
    extra = [c for c in ("rel_x", "extension", "spin") if pitches_fb[c].isna().any()]
    log.info("pitches_fb %d행. 핵심 특징 결측 %d, 그 밖 특징 결측률 %s", len(pitches_fb),
             int(pitches_fb[cfg["features"]["core"]].isna().sum().sum()),
             {c: round(float(pitches_fb[c].isna().mean()), 4) for c in extra})


if __name__ == "__main__":
    main()
