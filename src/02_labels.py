"""팔 부상 라벨 만들기 (단계 2.1). 규칙은 docs/SPEC.md 3.3절.

선수 이동 기록의 IL 등재 문구를 규칙대로 읽어
  data/processed/il_events.parquet    Statcast 투수의 모든 새 IL 등재와 분류 결과
  data/processed/labels_auto.csv      자동으로 '던지는 팔 팔꿈치·어깨'로 분류된 것
  data/processed/labels_review.csv    사람이 판단할 것 (decision에 '사례' 또는 '제외', note에 이유를 적는다.
                                      suggested·suggested_note는 기준에 따른 판독 제안이고, 확정은 decision 열로 한다)
을 만든다. 검토표를 다시 만들어도 이미 적어 둔 내용은 유지된다.

사용 예:
    python -m src.02_labels
    python -m src.02_labels --finalize      # 검토표를 다 채운 뒤: labels.csv, cases_raw.csv 생성 (단계 2.2)
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from src.common import labels as lb
from src.common.config import ROOT, load_config

RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
REVIEW = PROCESSED / "labels_review.csv"
log = logging.getLogger("pitchsignal.labels")


def finalize() -> None:
    """수기 검토 결과를 반영해 최종 라벨(labels.csv)과 투수-시즌별 첫 팔 부상 IL(cases_raw.csv)을 만든다 (단계 2.2)."""
    review = lb.read_review(REVIEW)
    waiting = lb.unreviewed(review)
    if len(waiting):
        print(f"아직 판단하지 않았거나 쓸 수 없는 줄이 {len(waiting)}건 있습니다 "
              f"(decision은 '{lb.CASE}' 또는 '{lb.EXCLUDED}', 사례라면 part는 elbow 또는 shoulder).")
        print(waiting[["event_id", "name", "il_date", "description", "part", "decision"]].to_string(index=False))
        raise SystemExit(1)
    labels = lb.final_labels(pd.read_csv(PROCESSED / "labels_auto.csv", encoding="utf-8-sig"), review)
    labels.to_csv(PROCESSED / "labels.csv", index=False, encoding="utf-8-sig")
    cases = lb.first_arm_il(labels)
    cases.to_csv(PROCESSED / "cases_raw.csv", index=False, encoding="utf-8-sig")
    decided = review["decision"].value_counts()
    log.info("최종 라벨 %d건, 투수-시즌별 첫 팔 부상 IL %d건. 수기 검토 %d건 중 사례 %d, 제외 %d", len(labels),
             len(cases), len(review), int(decided.get(lb.CASE, 0)), int(decided.get(lb.EXCLUDED, 0)))
    print(cases.groupby(["season", "part"]).size().unstack(fill_value=0).to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--finalize", action="store_true", help="수기 검토 결과를 반영해 최종 라벨을 만든다 (단계 2.2)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "labels.log", encoding="utf-8"), logging.StreamHandler()])
    if a.finalize:
        return finalize()
    cfg = load_config()
    transactions = pd.concat([pd.read_parquet(f) for f in sorted((RAW / "transactions").glob("*.parquet"))],
                             ignore_index=True)
    events = lb.build_events(transactions, pd.read_parquet(RAW / "people.parquet"), cfg["labels"])
    events.to_parquet(PROCESSED / "il_events.parquet", index=False)

    auto = events[events["verdict"] == "case"]
    auto[["event_id", "pitcher", "season", "il_date", "part", "description"]].to_csv(
        PROCESSED / "labels_auto.csv", index=False, encoding="utf-8-sig")

    review = events[events["verdict"] == "review"].assign(
        auto_reason=lambda d: d["why"].map(lb.WHY), suggested="", suggested_note="", decision="", note="")
    review = review[["event_id", "pitcher", "name", "il_date", "description", "auto_reason", "part",
                     "suggested", "suggested_note", "decision", "note"]]
    if REVIEW.exists():
        review = lb.carry_decisions(review, lb.read_review(REVIEW))
    review.to_csv(REVIEW, index=False, encoding="utf-8-sig")

    kind = events["part"].where(events["verdict"] == "case", events["verdict"])
    summary = events.groupby(["season", kind]).size().unstack(fill_value=0).rename_axis(columns=None)
    summary.to_csv(ROOT / "reports" / "tables" / "labels_summary.csv", encoding="utf-8-sig")
    log.info("IL 등재 %d건: 자동 사례 %d, 자동 제외 %d, 수기 검토 %d (이미 판단한 것 %d)", len(events), len(auto),
             int((events["verdict"] == "exclude").sum()), len(review), int((review["decision"] != "").sum()))
    print(summary.to_string())
    print("\n수기 검토 이유별 건수")
    print(review["auto_reason"].value_counts().to_string())
    print("\n자동 분류 무작위 20건 (문구와 분류가 맞는지 직접 확인)")
    sample = events[events["verdict"] != "review"].sample(20, random_state=cfg["seed"])
    pd.set_option("display.width", 250, "display.max_colwidth", 130)
    print(sample[["verdict", "part", "why", "il_date", "description"]].to_string(index=False))


if __name__ == "__main__":
    main()
