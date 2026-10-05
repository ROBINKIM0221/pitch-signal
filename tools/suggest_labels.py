"""수기 검토표(labels_review.csv)에 판독 제안을 채운다 (단계 2.2 보조).

기준: 부위가 던지는 팔의 팔꿈치·어깨(전완·굴곡근 포함)로 명시된 경우만 '사례'. 부위가 없거나 범위 밖이면 '제외'.
아래 규칙을 위에서부터 차례로 맞춰 보고 처음 맞는 것을 제안으로 적는다. 판단이 갈릴 수 있는 것은 이유 끝에
'(확인 필요)'를 붙였다. 제안은 suggested·suggested_note 열에만 적고, 확정은 사람이 decision 열에 한다.

사용 예:
    python tools/suggest_labels.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import labels as lb  # noqa: E402
from src.common.config import ROOT, load_config  # noqa: E402

REVIEW = ROOT / "data" / "processed" / "labels_review.csv"
CHECK = " (확인 필요)"
AUTO = "auto"       # 부위는 자동 분류가 읽은 값을 그대로 씀

# (사유 문장에 대한 정규식, 제안, 부위, 이유)
RULES = [
    # 팔 키워드와 다른 부위가 함께 나온 문구
    (r"lateral forearm", lb.CASE, "elbow", "전완 부상. 'lateral'이 광배근(lat)으로 잘못 걸렸음"),
    (r"fourth \w+ finger|wrist flexor", lb.EXCLUDED, "", "손가락·손목의 굴곡근"),
    (r"labrum in \w+ hip|hip flexor", lb.EXCLUDED, "", "고관절"),
    (r"tommy john|ucl reconstruction", lb.CASE, "elbow", "토미 존 수술(UCL 재건)은 던지는 팔에 받음"),
    (r"knee and \w+ shoulder surgery", lb.CASE, "shoulder", "어깨 수술이 함께 적힘. 좌우가 투구하는 손과 같은지" + CHECK),
    (r"forearm tendinitis and", lb.CASE, "elbow", "전완 부상이 함께 적힘"),
    (r"elbow injury and", lb.CASE, "elbow", "팔꿈치 부상이 함께 적힘"),
    (r"shoulder (latissimus|lat muscle)", lb.EXCLUDED, "", "어깨 쪽 광배근 부상. 광배근은 범위 밖" + CHECK),
    (r"lat/shoulder", lb.CASE, "shoulder", "광배근과 어깨가 함께 적힘" + CHECK),
    (r"shoulder bicep", lb.CASE, "shoulder", "어깨 쪽 이두근 힘줄. 어깨가 명시됨" + CHECK),
    # 좌우가 오타이거나 없는 팔 부상
    (r"\b(riht|rightt|rght|riight|let)\b", lb.CASE, AUTO, "Right/Left의 오타"),
    (r"^(ucl injury|flexor strain|forearm nerve|shoulder surgery)", lb.CASE, AUTO,
     "좌우가 적혀 있지 않음. 던지는 팔로 봄" + CHECK),
    (r"\bunar nerve", lb.CASE, "elbow", "ulnar의 오타. 좌우가 적혀 있지 않음. 던지는 팔로 봄" + CHECK),
    # 오타 때문에 목록에 걸리지 않은 팔꿈치·어깨
    (r"albow|elobw|eblow|elnow", lb.CASE, "elbow", "elbow의 오타"),
    (r"\bshould strain", lb.CASE, "shoulder", "shoulder의 오타"),
    # 어깨 둘레의 구조
    (r"subscapularis", lb.CASE, "shoulder", "견갑하근은 회전근개를 이루는 근육" + CHECK),
    (r"\bac joint", lb.CASE, "shoulder", "견봉쇄골관절은 어깨 관절" + CHECK),
    (r"teres|teras", lb.EXCLUDED, "", "대원근. 어깨 뒤쪽 근육이지만 어깨로 명시되지 않음" + CHECK),
    (r"scapula", lb.EXCLUDED, "", "어깨뼈(견갑골). 어깨 관절로 명시되지 않음" + CHECK),
    (r"deltoid", lb.EXCLUDED, "", "삼각근. 근육 이름만 적힘" + CHECK),
    (r"\bmcl\b", lb.EXCLUDED, "", "무릎인지 팔꿈치 안쪽 인대(=UCL)인지 문구로 알 수 없음" + CHECK),
    (r"thoracic outlet", lb.EXCLUDED, "", "흉곽출구증후군. 범위 밖"),
    (r"median nerve", lb.EXCLUDED, "", "정중신경. 팔꿈치·어깨로 명시되지 않음" + CHECK),
    (r"\barm\b|upper extremity|brachialis", lb.EXCLUDED, "", "부위가 팔꿈치·어깨로 명시되지 않음"),
]
DEFAULT = (lb.EXCLUDED, "", "팔꿈치·어깨가 아님")
BY_AUTO_REASON = {       # 문구가 아니라 기록 자체가 어긋난 경우는 제안하지 않고 확인할 것만 적는다
    lb.WHY["date_conflict"]: "기록일과 effective_date 중 어느 쪽이 맞는지 등판 기록으로 확인" + CHECK,
    lb.WHY["hand_mismatch"]: "투구하는 손을 확인한 뒤 판단" + CHECK,
}


def suggest(reason: str, part: str) -> tuple[str, str, str]:
    for pattern, decision, rule_part, note in RULES:
        if re.search(pattern, reason, re.IGNORECASE):
            return decision, part if rule_part == AUTO else rule_part, note
    return DEFAULT


def main():
    il_days = load_config()["labels"]["il_days"]
    review = pd.read_csv(REVIEW, encoding="utf-8-sig").fillna("")
    for i, row in review.iterrows():
        if row["suggested"] or row["decision"]:
            continue
        if row["auto_reason"] in BY_AUTO_REASON:
            review.loc[i, "suggested_note"] = BY_AUTO_REASON[row["auto_reason"]]
            continue
        reason = lb.parse_placement(row["description"], il_days)["reason"]
        review.loc[i, ["suggested", "part", "suggested_note"]] = suggest(reason, row["part"])
    review.to_csv(REVIEW, index=False, encoding="utf-8-sig")
    print(review["suggested"].replace("", "(제안 없음)").value_counts().to_string())
    print(f"'(확인 필요)'가 붙은 줄: {int(review['suggested_note'].str.contains('확인 필요').sum())}건 / 전체 {len(review)}건")


if __name__ == "__main__":
    main()
