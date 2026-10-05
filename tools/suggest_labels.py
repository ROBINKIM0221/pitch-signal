"""수기 검토표(labels_review.csv)에 판독 제안을 채운다 (단계 2.2 보조).

기준: 부위가 던지는 팔의 팔꿈치·어깨(전완·굴곡근 포함)로 명시된 경우만 '사례'. 부위가 없거나 범위 밖이면 '제외'.
아래 규칙을 위에서부터 차례로 맞춰 보고 처음 맞는 것을 제안으로 적는다. 판단이 갈릴 수 있는 것은 이유 끝에
'(확인 필요)'를 붙였다. 제안은 suggested·suggested_note 열에 적고, 확정은 사람이 decision 열에 한다.
기록일과 effective_date가 어긋난 기록은 기준일(il_date)도 제안한 날짜로 바꿔 적는다(원래 날짜는 이유에 남김).

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
NEIGHBOURS = 100      # 기준일을 가늠할 때 보는, 거래 번호가 가까운 기록 수


def suggest(reason: str, part: str) -> tuple[str, str, str]:
    for pattern, decision, rule_part, note in RULES:
        if re.search(pattern, reason, re.IGNORECASE):
            return decision, part if rule_part == AUTO else rule_part, note
    return DEFAULT


def suggest_date(event_id: int, pitcher: int, days: int, dates: pd.DataFrame, outings: pd.DataFrame):
    """기록일과 effective_date가 어긋난 기록의 기준일 제안: (기준일 또는 None, 이유).

    거래 번호는 시간순으로 붙으므로, 번호가 가까운 기록들의 날짜(중앙값)와 가까운 쪽을 고른다.
    고른 날부터 최소 등재 일수 안에 등판 기록이 있으면 맞지 않으므로 다른 날짜를 보거나 확인 대상으로 남긴다.
    """
    recorded, effective = dates.loc[event_id, "date"], dates.loc[event_id, "effective_date"]
    at = dates.index.get_loc(event_id)
    near = dates["date"].iloc[max(0, at - NEIGHBOURS // 2): at + NEIGHBOURS // 2 + 1].drop(event_id).median()
    mine = outings.loc[outings["pitcher"] == pitcher, "game_date"]

    def possible(day):
        return not ((mine >= day) & (mine < day + pd.Timedelta(days=days))).any()

    first, second = sorted((recorded, effective), key=lambda d: abs(d - near))
    said = f"기록일 {recorded:%Y-%m-%d}, effective_date {effective:%Y-%m-%d}, 번호가 가까운 기록들은 {near:%Y-%m-%d} 무렵"
    if possible(first):
        return first, f"기준일 {first:%Y-%m-%d} ({said})"
    if possible(second):
        return second, f"기준일 {second:%Y-%m-%d} ({said}. 가까운 쪽은 그 뒤 등판이 있어 맞지 않음)" + CHECK
    return None, f"두 날짜 모두 그 뒤에 등판 기록이 있음 ({said})" + CHECK


def main():
    il_days = load_config()["labels"]["il_days"]
    review = lb.read_review(REVIEW)
    raw = ROOT / "data" / "raw" / "transactions"
    dates = pd.concat([pd.read_parquet(f, columns=["id", "date", "effective_date"]) for f in sorted(raw.glob("*.parquet"))])
    dates = dates.drop_duplicates("id").set_index("id").sort_index().apply(pd.to_datetime)
    outings = pd.read_parquet(ROOT / "data" / "processed" / "outings.parquet", columns=["pitcher", "game_date"])
    for i, row in review.iterrows():
        if row["suggested"] or row["decision"]:
            continue
        placement = lb.parse_placement(row["description"], il_days)
        if row["auto_reason"] == lb.WHY["hand_mismatch"]:
            review.loc[i, "suggested_note"] = "투구하는 손을 확인한 뒤 판단" + CHECK
        elif row["auto_reason"] == lb.WHY["date_conflict"]:      # 문구는 던지는 팔 팔꿈치·어깨. 날짜만 정하면 됨
            day, note = suggest_date(row["event_id"], row["pitcher"], placement["days"], dates, outings)
            if day is not None:
                review.loc[i, ["il_date", "suggested"]] = [f"{day:%Y-%m-%d}", lb.CASE]
            review.loc[i, "suggested_note"] = note
        else:
            review.loc[i, ["suggested", "part", "suggested_note"]] = suggest(placement["reason"], row["part"])
    review.to_csv(REVIEW, index=False, encoding="utf-8-sig")
    print(review["suggested"].replace("", "(제안 없음)").value_counts().to_string())
    print(f"'(확인 필요)'가 붙은 줄: {int(review['suggested_note'].str.contains('확인 필요').sum())}건 / 전체 {len(review)}건")


if __name__ == "__main__":
    main()
