"""부상 라벨 규칙 (SPEC 3.3). IL 등재 문구를 읽어 던지는 팔의 팔꿈치·어깨 부상을 가려낸다."""
from __future__ import annotations

import re
from datetime import date, datetime

import pandas as pd

PLACED = re.compile(
    r"placed (?P<pos>\S+) (?P<name>.+?) on the (?P<days>\d+)[- ]day injured list"
    r"(?: retroactive to (?P<retro>[A-Za-z]+ \d{1,2}, \d{4}))?\.?\s*(?P<reason>.*)$")
SIDE = re.compile(r"\b(right|left)\b", re.IGNORECASE)

# 분류 이유 코드와 수기 검토표에 적는 설명
WHY = {
    "ok": "던지는 팔 팔꿈치·어깨",
    "other_arm": "반대쪽 팔",
    "other_part": "팔꿈치·어깨가 아닌 부위",
    "no_reason": "사유 문구가 없어 부위를 알 수 없음",
    "unknown_part": "목록에 없는 부위",
    "no_side": "좌우 없음",
    "both_sides": "좌우가 둘 다 나옴",
    "arm_and_other_part": "팔 키워드와 다른 부위가 함께 있음",
    "two_parts": "팔꿈치와 어깨가 함께 있음",
    "hand_unknown": "투구하는 손 정보 없음",
    "not_pitcher": "투수로 등재되지 않음",
    "hand_mismatch": "문구의 RHP/LHP와 선수 정보의 투구하는 손이 다름",
    "date_conflict": "기록일과 effective_date가 서로 안 맞음",
}
PITCHER_POS = {"RHP": "R", "LHP": "L"}


def parse_placement(description: str, il_days: list[int]) -> dict | None:
    """새 IL 등재 문구를 pos·name·days·retro·reason으로 나눈다.

    새 등재가 아니거나(transferred·activated 등) 일수가 il_days에 없으면 None.
    """
    m = PLACED.search(description or "")
    if m is None or int(m["days"]) not in il_days:
        return None
    retro = datetime.strptime(m["retro"], "%B %d, %Y").date() if m["retro"] else None
    return {"pos": m["pos"], "name": m["name"], "days": int(m["days"]), "retro": retro, "reason": m["reason"].strip()}


def il_date(retro: date | None, effective_date: str | None, tx_date: str, max_retro_days: int) -> tuple[date, bool]:
    """IL 기준일과 '날짜가 서로 안 맞음' 표시. 문구의 소급일 → effective_date → 기록일 순으로 쓴다.

    effective_date가 기록일보다 뒤이거나 max_retro_days보다 더 앞이면 믿지 않고 기록일을 쓴다(표시 True).
    """
    recorded = date.fromisoformat(tx_date)
    if retro is not None:
        return retro, False
    if effective_date is None:
        return recorded, False
    effective = date.fromisoformat(effective_date)
    if 0 <= (recorded - effective).days <= max_retro_days:
        return effective, False
    return recorded, True


def _has(words: list[str], text: str) -> bool:
    return any(re.search(r"\b" + re.escape(w), text, re.IGNORECASE) for w in words)


def classify(reason: str, pitch_hand: str | None, rules: dict) -> tuple[str, str, str]:
    """IL 사유 문장을 (판정, 부위, 이유 코드)로 분류한다.

    판정: 'case'(던지는 팔 팔꿈치·어깨) | 'exclude' | 'review'(사람이 판단)
    부위: 'elbow' | 'shoulder' | ''        이유 코드: WHY의 키
    """
    if not reason.strip():
        return "exclude", "", "no_reason"       # 부위를 알 수 없는 등재는 사례로 치지 않는다
    shoulder = _has(rules["shoulder_keywords"], reason)
    elbow = _has([w for w in rules["arm_keywords"] if w not in rules["shoulder_keywords"]], reason)
    other = _has(rules["exclude_keywords"], reason)
    if not (shoulder or elbow):
        return ("exclude", "", "other_part") if other else ("review", "", "unknown_part")
    if shoulder and elbow:
        return "review", "", "two_parts"
    part = "shoulder" if shoulder else "elbow"
    if other:
        return "review", part, "arm_and_other_part"
    sides = {s.lower() for s in SIDE.findall(reason)}
    if len(sides) != 1:
        return "review", part, "both_sides" if sides else "no_side"
    if pitch_hand not in ("R", "L"):
        return "review", part, "hand_unknown"
    return ("case", part, "ok") if sides.pop()[0].upper() == pitch_hand else ("exclude", part, "other_arm")


def build_events(transactions: pd.DataFrame, people: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """선수 이동 기록에서 Statcast에 나온 투수의 새 IL 등재를 뽑아 분류한 표를 만든다.

    같은 투수·기준일·문구가 반복된 기록은 하나만 남긴다. 야수로 등재된 기록은 'exclude'로 남겨 둔다
    (대조군의 '기준일 앞뒤 IL 기록 없음' 확인에 쓰기 위함).
    """
    hands = dict(zip(people["id"], people["pitch_hand"]))
    rows = []
    for t in transactions.itertuples(index=False):
        p = parse_placement(t.description, rules["il_days"])
        if p is None or t.person_id not in hands:
            continue
        effective = t.effective_date if isinstance(t.effective_date, str) else None
        when, conflict = il_date(p["retro"], effective, t.date, rules["max_retro_days"])
        listed, known = PITCHER_POS.get(p["pos"]), hands[t.person_id]
        if listed is None:
            verdict, part, why = "exclude", "", "not_pitcher"
        else:
            verdict, part, why = classify(p["reason"], listed, rules)
            if why in ("ok", "other_arm") and known in ("R", "L") and known != listed:
                verdict, why = "review", "hand_mismatch"
            elif verdict == "case" and conflict:
                verdict, why = "review", "date_conflict"
        rows.append({"event_id": int(t.id), "pitcher": int(t.person_id), "name": t.person_name, "season": when.year,
                     "il_date": when, "days": p["days"], "pos": p["pos"], "reason": p["reason"],
                     "verdict": verdict, "part": part, "why": why, "description": t.description})
    events = pd.DataFrame(rows)
    return events.drop_duplicates(["pitcher", "il_date", "description"]).reset_index(drop=True)


def carry_decisions(review: pd.DataFrame, previous: pd.DataFrame) -> pd.DataFrame:
    """사람이 이미 적어 둔 decision·note·part를 event_id로 찾아 새 검토표에 옮긴다 (다시 만들 때 지워지지 않게)."""
    old = previous.drop_duplicates("event_id").set_index("event_id")
    out = review.copy()
    for col in ("decision", "note", "part", "suggested", "suggested_note"):
        if col in old.columns and col in out.columns:
            kept = out["event_id"].map(old[col])
            out[col] = kept.where(kept.notna() & (kept != ""), out[col])
    return out
