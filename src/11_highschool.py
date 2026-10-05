"""고교 투구수 모듈 (단계 6.5~6.6). 규칙은 docs/SPEC.md 3.14절. 학교·투수는 가명 코드만 다룬다.

입력: data/highschool/input.xlsx (templates/highschool_input.xlsx를 복사해 채운 것)
  --check   입력 검사. 오류 줄을 화면에 보여 주고, 학교별 요약을 reports/tables/hs_input_check.csv로,
            원래 기록과 다시 대조할 경기 목록을 data/highschool/recheck_games.csv로 저장한다 (단계 6.5)
  (옵션 없음) 규정 위반과 누적 부하 계산 (단계 6.6)
            data/processed/hs_daily.parquet      투수별 하루 단위 값
            data/processed/hs_violations.csv     위반 목록 (투수 코드와 날짜가 있어 저장소에는 올리지 않는다)
            reports/tables/hs_summary.csv        학교별 요약

사용 예:
    python -m src.11_highschool --check
    python -m src.11_highschool
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from src.common import highschool as hs
from src.common.config import ROOT, load_config

INPUT = ROOT / "data" / "highschool" / "input.xlsx"
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
log = logging.getLogger("pitchsignal.highschool")


def check(rows: pd.DataFrame, cfg: dict) -> None:
    rules = cfg["highschool"]
    found = hs.problems(rows, rules)
    table = pd.DataFrame({"입력 줄 수": rows.groupby("school").size(),
                          "경기 수": rows.drop_duplicates(hs.GAME).groupby("school").size(),
                          "투수 수": rows.groupby("school")["pitcher"].nunique(),
                          "투구수 빈 줄 비율": hs.missing_share(rows).round(3)})
    table = table.join(found.groupby(["school", "kind"]).size().unstack(fill_value=0)).fillna(0).rename_axis("학교")
    table.to_csv(TABLES / "hs_input_check.csv", encoding="utf-8-sig")
    games = hs.recheck_games(rows, rules["recheck_frac"], cfg["seed"])
    games.to_csv(INPUT.parent / "recheck_games.csv", index=False, encoding="utf-8-sig")

    log.info("입력 %d줄, 오류 %d건, 재대조할 경기 %d개", len(rows), len(found), len(games))
    if len(found):
        print("고칠 줄 (row는 엑셀 줄 번호)")
        print(found.to_string(index=False))
    print(table.to_string())
    low = table.index[table["투구수 빈 줄 비율"] > 1 - rules["min_pitch_count_coverage"]]
    if len(low):
        print(f"투구수 기재율이 {rules['min_pitch_count_coverage']:.0%}에 못 미치는 학교: {', '.join(low)}")
    print(f"\n원래 기록과 다시 대조할 경기 ({rules['recheck_frac']:.0%} 무작위)")
    print(games.assign(date=games["date"].dt.strftime("%Y-%m-%d")).to_string(index=False))


def compute(rows: pd.DataFrame, cfg: dict) -> None:
    rules = cfg["highschool"]
    if len(hs.problems(rows, rules)):
        raise SystemExit("입력 오류가 남아 있습니다. python -m src.11_highschool --check 로 확인하고 고친 뒤 다시 실행하세요.")
    daily = hs.daily_table(rows, rules)
    found = hs.violations(rows, daily, rules)
    table = hs.summary(daily, found)
    daily.to_parquet(PROCESSED / "hs_daily.parquet", compression="zstd", index=False)
    found.to_csv(PROCESSED / "hs_violations.csv", index=False, encoding="utf-8-sig")
    table.to_csv(TABLES / "hs_summary.csv", index=False, encoding="utf-8-sig")

    log.info("투수 %d명, 하루 단위 %d줄, 위반·판정 불가 %d건", daily["pitcher"].nunique(), len(daily), len(found))
    print(table.to_string(index=False))
    print("\n종류별 건수 (unknown = 투구 수 기록이 없어 판정 불가, foreign_* = 해외 규정을 적용했다면 위반)")
    print(found.groupby(["school", "rule"]).size().unstack(fill_value=0).to_string())
    skipped = [name for name, rule in rules["foreign_rules"].items() if not rule]
    if skipped:
        print("계산하지 않은 해외 규정 (설정에 값이 없음):", ", ".join(skipped))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="입력 검사와 재대조할 경기 목록 (단계 6.5)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "highschool.log", encoding="utf-8"), logging.StreamHandler()])
    if not INPUT.exists():
        raise SystemExit(f"{INPUT.relative_to(ROOT)} 파일이 없습니다. templates/highschool_input.xlsx를 복사해 채워 주세요 (단계 6.4).")
    rows = hs.read_input(INPUT)
    (check if a.check else compute)(rows, load_config())


if __name__ == "__main__":
    main()
