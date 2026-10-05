"""사례와 대조군 확정 (단계 2.6). 규칙은 docs/SPEC.md 3.13.2절. 탐지율 같은 성능 지표는 계산하지 않는다.

최종 라벨(data/processed/cases_raw.csv, 단계 2.2)과 등판 표로
  data/processed/cases.csv       확정 사례 (case_id = IL 기록 번호)
  data/processed/controls.csv    사례마다 고른 대조군과 가상 기준일
  data/processed/windows.csv     사례·대조군의 관찰 창 등판 목록
  reports/tables/cases_summary.csv, cases_dropped.csv    수량 표
를 만든다.

사용 예:
    python -m src.05_cases
"""
from __future__ import annotations

import logging

import pandas as pd

from src.common import baseline_window as bw
from src.common import cases as cs
from src.common.config import ROOT, load_config

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
log = logging.getLogger("pitchsignal.cases")


def build(raw: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """투수-시즌별 첫 팔 부상 IL 표 → (사례, 빠진 것과 이유, 대조군)."""
    rules = cfg["evaluation"]
    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    outings["phase"] = bw.phase(outings, cfg["baseline"])
    people = pd.read_parquet(ROOT / "data" / "raw" / "people.parquet")
    il = pd.read_parquet(PROCESSED / "il_events.parquet", columns=["pitcher", "il_date"])
    il["il_date"] = pd.to_datetime(il["il_date"])
    cases, dropped = cs.build_cases(raw, outings, people, rules)
    arm_il = raw if rules["control_no_arm_il_in_season"] else raw.iloc[:0]
    return cases, dropped, cs.match_controls(cases, outings, il, arm_il, people, rules)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "cases.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    source = PROCESSED / "cases_raw.csv"
    if not source.exists():
        raise SystemExit("data/processed/cases_raw.csv가 없습니다. 수기 검토를 마친 뒤 "
                         "python -m src.02_labels --finalize 를 먼저 실행하세요 (단계 2.2).")
    raw = pd.read_csv(source, encoding="utf-8-sig")
    cases, dropped, controls = build(raw, cfg)

    columns = ["case_id", "pitcher", "season", "role", "part", "il_date", "age", "cum_pitches"]
    cases[columns].round({"age": 2}).to_csv(PROCESSED / "cases.csv", index=False, encoding="utf-8-sig")
    controls.drop(columns="window_games").round({"age": 2}).to_csv(PROCESSED / "controls.csv", index=False,
                                                                   encoding="utf-8-sig")
    cs.window_table(cases, controls).to_csv(PROCESSED / "windows.csv", index=False, encoding="utf-8-sig")
    table = cs.count_table(cases, controls, cfg["data"]["split"])
    table.to_csv(TABLES / "cases_summary.csv", encoding="utf-8-sig")
    why = dropped.groupby(["season", "why"]).size().unstack(fill_value=0).rename_axis(index="시즌", columns=None)
    why.to_csv(TABLES / "cases_dropped.csv", encoding="utf-8-sig")

    log.info("투수-시즌별 첫 팔 부상 IL %d건 → 사례 %d건, 대조군 %d명", len(raw), len(cases), len(controls))
    print(table.to_string())
    print("\n사례에서 빠진 이유 (시즌별 건수)")
    print(why.to_string())
    print("\n대조군과 사례의 누적 투구 수 차이:", controls["dist"].describe().round(1).to_dict())


if __name__ == "__main__":
    main()
