"""Statcast 원데이터 내려받기 (단계 1.1~1.2).

주 단위(7일)로 받아 data/raw/statcast/<시즌>/<MMDD>.parquet로 저장한다. 이미 받은 주는 건너뛰므로
중간에 끊기면 같은 명령을 다시 실행하면 된다.

사용 예:
    python -m src.01_download --test-week
    python -m src.01_download --all                 # 설정의 모든 시즌. --parallel을 붙이면 하루치 요청을 동시에 보냄
    python -m src.01_download --season 2023
    python -m src.01_download --season 2023 --start 2023-06-01 --end 2023-06-14
"""
from __future__ import annotations

import argparse
import logging
from datetime import date

import pandas as pd

from src.common import mlb_api as api
from src.common import statcast as st
from src.common.config import ROOT, load_config

RAW = ROOT / "data" / "raw" / "statcast"
RAW_TEST = ROOT / "data" / "raw" / "statcast_test"      # 시험 주는 전체 다운로드와 겹치므로 따로 둔다
TRANSACTIONS = ROOT / "data" / "raw" / "transactions"
PEOPLE = ROOT / "data" / "raw" / "people.parquet"
log = logging.getLogger("pitchsignal.download")


def setup_log(name: str) -> None:
    path = ROOT / "reports" / "logs" / f"download_{name}.log"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(path, encoding="utf-8"), logging.StreamHandler()])


def make_fetch(parallel: bool):
    def fetch(start: date, end: date) -> pd.DataFrame:
        from pybaseball import statcast
        return statcast(start_dt=str(start), end_dt=str(end), verbose=False, parallel=parallel)
    return fetch


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


def save_transactions(cfg: dict) -> pd.DataFrame:
    """선수 이동 기록을 받아 시즌(달력 연도)별 파일로 저장하고 시즌별 건수를 돌려준다."""
    df = api.fetch_transactions(cfg).drop_duplicates()
    year = pd.to_datetime(df["date"].fillna(df["effective_date"])).dt.year
    TRANSACTIONS.mkdir(parents=True, exist_ok=True)
    rows = []
    for season, part in df.groupby(year):
        part.to_parquet(TRANSACTIONS / f"{int(season)}.parquet", compression="zstd", index=False)
        il = part["description"].str.contains("injured list", case=False, na=False)
        rows.append({"season": int(season), "transactions": len(part), "injured_list": int(il.sum())})
    if year.isna().any():
        log.warning("날짜가 없어 저장하지 않은 기록 %d건", int(year.isna().sum()))
    return pd.DataFrame(rows)


def save_people(cfg: dict) -> pd.DataFrame:
    """내려받은 Statcast에 나온 모든 투수의 이름·생년월일·투구하는 손을 받아 저장한다."""
    files = sorted(RAW.rglob("*.parquet"))
    ids = pd.concat([pd.read_parquet(f, columns=["pitcher"]) for f in files])["pitcher"].dropna().astype(int)
    people = api.fetch_people(ids.unique().tolist(), cfg)
    people.to_parquet(PEOPLE, compression="zstd", index=False)
    return people


def data_check(cfg: dict) -> pd.DataFrame:
    """시즌별 점검표: Statcast 요약과 선수 이동 기록 건수 (단계 1.4). 성능 지표는 계산하지 않는다."""
    keys = ["game_pk", "game_date", "home_team", "away_team", "pitcher", "at_bat_number", "pitch_number"]
    checks = cfg["data"]["check_columns"]
    rows = []
    for season in cfg["data"]["seasons"]:
        df = st.load_season(RAW, season, keys + checks)
        tx = pd.read_parquet(TRANSACTIONS / f"{season}.parquet", columns=["description"])["description"]
        rows.append({"season": season, "weeks": len(list((RAW / str(season)).glob("*.parquet"))),
                     **st.season_summary(df, checks, cfg["data"]["min_team_games"]),
                     "transactions": len(tx),
                     "injured_list": int(tx.str.contains("injured list", case=False, na=False).sum())})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    ap.add_argument("--start", type=date.fromisoformat, help="YYYY-MM-DD (기본: 설정의 download_window)")
    ap.add_argument("--end", type=date.fromisoformat)
    ap.add_argument("--test-week", action="store_true", help="설정의 시험 주만 받아 열을 점검한다")
    ap.add_argument("--all", action="store_true", help="설정의 모든 시즌을 차례로 받는다")
    ap.add_argument("--parallel", action="store_true", help="한 주 안의 하루치 요청을 동시에 보낸다 (빠르지만 서버 부담이 큼)")
    ap.add_argument("--transactions", action="store_true", help="MLB Stats API 선수 이동 기록을 받는다")
    ap.add_argument("--people", action="store_true", help="받아 둔 Statcast의 모든 투수 정보를 받는다")
    ap.add_argument("--check", action="store_true", help="받은 데이터의 시즌별 점검표를 만든다")
    a = ap.parse_args()
    cfg = load_config()
    game_type = cfg["data"]["game_type"]
    fetch = make_fetch(a.parallel)

    if a.check:
        setup_log("check")
        table = data_check(cfg)
        out = ROOT / "reports" / "tables" / "data_check.csv"
        table.to_csv(out, index=False, encoding="utf-8-sig")
        log.info("데이터 점검표 저장 → %s", out)
        print(table.set_index("season").T.to_string(float_format=lambda v: f"{v:.4f}"))
        return

    if a.transactions:
        setup_log("transactions")
        table = save_transactions(cfg)
        log.info("선수 이동 기록 %d건 저장 → %s", int(table["transactions"].sum()), TRANSACTIONS)
        print(table.to_string(index=False))
        return

    if a.people:
        setup_log("people")
        people = save_people(cfg)
        log.info("선수 정보 %d명 저장 (생년월일 결측 %d, 투구하는 손 결측 %d) → %s", len(people),
                 int(people["birth_date"].isna().sum()), int(people["pitch_hand"].isna().sum()), PEOPLE)
        return

    if a.all:
        setup_log("all")
        summary = st.download_seasons(cfg, cfg["data"]["seasons"], RAW, fetch)
        for season in cfg["data"]["seasons"]:
            warn_missing_columns(RAW / str(season), cfg)
        log.info("전체 완료. 끝까지 실패한 주 %d개 %s", len(summary["failed"]), [str(d) for d in summary["failed"]])
        print(pd.DataFrame(summary["seasons"]).to_string(index=False))
        return

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
