"""Statcast 원데이터 내려받기 (단계 1.1).

주 단위(7일)로 받아 data/raw/statcast/<시즌>/<MMDD>.parquet로 저장한다. 이미 받은 주는 건너뛴다.

사용 예:
    python -m src.01_download --test-week
    python -m src.01_download --season 2023
    python -m src.01_download --season 2023 --start 2023-06-01 --end 2023-06-14
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

import pandas as pd

from src.common import statcast as st
from src.common.config import ROOT, load_config

RAW = ROOT / "data" / "raw" / "statcast"
RAW_TEST = ROOT / "data" / "raw" / "statcast_test"      # 시험 주는 전체 다운로드와 겹치므로 따로 둔다
log = logging.getLogger("pitchsignal.download")


def setup_log(name: str) -> None:
    path = ROOT / "reports" / "logs" / f"download_{name}.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler()])


def fetch(start: date, end: date) -> pd.DataFrame:
    from pybaseball import statcast
    return statcast(start_dt=str(start), end_dt=str(end), verbose=False, parallel=False)


def warn_missing_columns(root, cfg: dict) -> None:
    files = sorted(root.rglob("*.parquet"))
    if not files:
        return
    have = set(pd.read_parquet(files[0]).columns)
    missing = [c for c in cfg["data"]["statcast_columns"] if c not in have]
    if missing:
        log.warning("분석에 쓰는 열이 원데이터에 없음: %s", missing)


def column_check(root, cfg: dict) -> pd.DataFrame:
    """시즌별 행 수, 투수 수, 점검 열의 결측률."""
    rows = []
    for season_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        df = pd.concat([pd.read_parquet(f) for f in sorted(season_dir.glob("*.parquet"))], ignore_index=True)
        rows.append({"season": int(season_dir.name), "rows": len(df), "pitchers": df["pitcher"].nunique(),
                     "game_types": ",".join(sorted(df["game_type"].unique())),
                     **{f"na_{c}": r for c, r in st.missing_rates(df, cfg["data"]["check_columns"]).items()}})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    ap.add_argument("--start", type=date.fromisoformat, help="YYYY-MM-DD (기본: 설정의 download_window)")
    ap.add_argument("--end", type=date.fromisoformat)
    ap.add_argument("--test-week", action="store_true", help="설정의 시험 주만 받아 열을 점검한다")
    a = ap.parse_args()
    cfg = load_config()
    game_type = cfg["data"]["game_type"]

    if a.test_week:
        setup_log("test")
        weeks = [(date.fromisoformat(s), date.fromisoformat(e)) for s, e in cfg["data"]["test_weeks"]]
        result = st.download_weeks(weeks, RAW_TEST, fetch, game_type)
        warn_missing_columns(RAW_TEST, cfg)
        table = column_check(RAW_TEST, cfg)
        out = ROOT / "reports" / "tables" / "column_check.csv"
        table.to_csv(out, index=False, encoding="utf-8-sig")
        log.info("저장 %d주, 건너뜀 %d주, 실패 %d주 → %s", len(result["saved"]), len(result["skipped"]),
                 len(result["failed"]), out)
        print(table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))
        return

    if a.season is None:
        ap.error("--season 또는 --test-week가 필요합니다")
    setup_log(str(a.season))
    start, end = st.season_window(cfg, a.season)
    weeks = st.week_ranges(a.start or start, a.end or end)
    result = st.download_weeks(weeks, RAW, fetch, game_type)
    warn_missing_columns(RAW / str(a.season), cfg)
    log.info("%d 시즌: 저장 %d주, 건너뜀 %d주, 실패 %d주 %s", a.season, len(result["saved"]),
             len(result["skipped"]), len(result["failed"]), [str(d) for d in result["failed"]])


if __name__ == "__main__":
    main()
