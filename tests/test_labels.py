"""부상 라벨 규칙 테스트 (SPEC 3.3). 실행: python -m pytest -q"""
from datetime import date

import pandas as pd
import pytest

from src.common import labels as lb

RULES = {
    "il_days": [10, 15, 60],
    "max_retro_days": 10,
    "arm_keywords": ["elbow", "ucl", "ulnar", "tommy john", "forearm", "flexor", "pronator",
                     "shoulder", "rotator cuff", "labrum", "capsule"],
    "shoulder_keywords": ["shoulder", "rotator cuff", "labrum", "capsule"],
    "exclude_keywords": ["oblique", "hamstring", "ankle", "knee", "back", "hip", "groin", "quad", "calf", "foot",
                         "toe", "illness", "concussion", "covid", "finger", "blister", "wrist", "thumb", "hand",
                         "neck", "lat", "triceps", "bicep", "pectoral", "trapezius", "lumbar", "spine",
                         "cervical", "rib", "intercostal", "abdominal", "adductor", "patella", "achilles",
                         "shin", "glute", "leg", "appendicitis", "appendectomy", "viral", "infection"],
}


def parse(text):
    return lb.parse_placement(text, RULES["il_days"])


def test_parse_splits_position_name_days_and_reason():
    p = parse("New York Mets placed RHP Tylor Megill on the 15-day injured list. Right shoulder strain.")
    assert (p["pos"], p["name"], p["days"], p["retro"], p["reason"]) == \
           ("RHP", "Tylor Megill", 15, None, "Right shoulder strain.")


def test_parse_reads_retroactive_date():
    p = parse("Seattle Mariners placed RHP Bryce Miller on the 15-day injured list retroactive to June 7, 2025. "
              "Right elbow inflammation.")
    assert p["retro"] == date(2025, 6, 7)
    assert p["reason"] == "Right elbow inflammation."


def test_parse_handles_periods_in_names():
    p = parse("Atlanta Braves placed LHP A.J. Minter on the 10-day injured list. Left shoulder inflammation.")
    assert (p["name"], p["reason"]) == ("A.J. Minter", "Left shoulder inflammation.")


def test_parse_keeps_empty_reason_when_none_is_given():
    assert parse("Chicago Cubs placed RHP Some One on the 10-day injured list.")["reason"] == ""


@pytest.mark.parametrize("text", [
    "Arizona Diamondbacks transferred RHP Cristian Mena from the 15-day injured list to the 60-day injured list. "
    "Right shoulder strain.",
    "Baltimore Orioles activated CF Cedric Mullins from the 10-day injured list.",
    "Boston Red Sox placed C Some One on the 7-day injured list. Concussion.",
    "Texas Rangers traded RHP Art Warren to Cincinnati Reds for cash.",
])
def test_parse_ignores_everything_but_new_placements_of_allowed_length(text):
    assert parse(text) is None


def test_il_date_prefers_retroactive_text_then_effective_date():
    assert lb.il_date(date(2025, 6, 9), "2025-06-08", "2025-06-10", 10) == (date(2025, 6, 9), False)
    assert lb.il_date(None, "2021-04-13", "2021-04-16", 10) == (date(2021, 4, 13), False)
    assert lb.il_date(None, None, "2021-04-16", 10) == (date(2021, 4, 16), False)


def test_il_date_falls_back_to_transaction_date_and_flags_impossible_effective_dates():
    assert lb.il_date(None, "2023-04-14", "2021-04-16", 10) == (date(2021, 4, 16), True)     # 기록일보다 뒤
    assert lb.il_date(None, "2021-03-01", "2021-04-16", 10) == (date(2021, 4, 16), True)     # 소급 한도를 넘김


@pytest.mark.parametrize("reason, hand, expected", [
    ("Right elbow inflammation.", "R", ("case", "elbow", "ok")),
    ("Left shoulder strain.", "L", ("case", "shoulder", "ok")),
    ("Right UCL sprain.", "R", ("case", "elbow", "ok")),
    ("Recovery from right shoulder surgery.", "R", ("case", "shoulder", "ok")),      # 좌우가 문장 중간에 있어도 읽음
    ("Left shoulder strain.", "R", ("exclude", "shoulder", "other_arm")),
    ("Right hamstring strain.", "R", ("exclude", "", "other_part")),
    ("Tommy John surgery.", "R", ("review", "elbow", "no_side")),
    ("Riht pronator strain.", "R", ("review", "elbow", "no_side")),                  # 오타
    ("Right hip flexor strain.", "R", ("review", "elbow", "arm_and_other_part")),
    ("Right thumb UCL sprain.", "R", ("review", "elbow", "arm_and_other_part")),
    ("Right knee and left shoulder surgery.", "L", ("review", "shoulder", "arm_and_other_part")),
    ("Right shoulder and right elbow inflammation.", "R", ("review", "", "two_parts")),
    ("Right forearm tightness and left elbow soreness.", "R", ("review", "elbow", "both_sides")),
    ("", "R", ("exclude", "", "no_reason")),                                         # 부위를 알 수 없으므로 제외
    ("Right lat strain.", "R", ("exclude", "", "other_part")),                       # 범위 밖 부위 (광배근)
    ("Left shoulder biceps tendinitis.", "L", ("review", "shoulder", "arm_and_other_part")),
    ("Right teres major strain.", "R", ("review", "", "unknown_part")),
    ("Right arm fatigue.", "R", ("review", "", "unknown_part")),
    ("Right elbow inflammation.", None, ("review", "elbow", "hand_unknown")),
])
def test_classify(reason, hand, expected):
    assert lb.classify(reason, hand, RULES) == expected


def _tx(event_id, person_id, text, tx_date="2023-07-01", effective="2023-07-01"):
    return {"id": event_id, "person_id": person_id, "person_name": f"P{person_id}", "date": tx_date,
            "effective_date": effective, "description": text}


def test_build_events_keeps_new_placements_of_statcast_pitchers_once():
    elbow = "T placed RHP P10 on the 15-day injured list retroactive to June 8, 2023. Right elbow inflammation."
    tx = pd.DataFrame([
        _tx(1, 10, elbow, "2023-06-10", "2023-06-08"),
        _tx(2, 10, elbow, "2023-06-10", "2023-06-08"),                                         # 같은 기록이 두 번
        _tx(3, 11, "T placed LHP P11 on the 15-day injured list. Left hamstring strain."),
        _tx(4, 12, "T placed SS P12 on the 10-day injured list. Right shoulder strain."),      # 야수로 등재
        _tx(5, 99, "T placed RHP P99 on the 15-day injured list. Right elbow sprain."),        # Statcast에 없는 선수
        _tx(6, 10, "T activated RHP P10 from the 15-day injured list.", "2023-08-01", None),
    ])
    people = pd.DataFrame({"id": [10, 11, 12], "pitch_hand": ["R", "L", "R"]})
    ev = lb.build_events(tx, people, RULES)
    assert list(ev["event_id"]) == [1, 3, 4]
    assert list(ev["verdict"]) == ["case", "exclude", "exclude"]
    assert list(ev["why"]) == ["ok", "other_part", "not_pitcher"]
    first = ev.iloc[0]
    assert (first["pitcher"], first["season"], first["il_date"], first["part"]) == (10, 2023, date(2023, 6, 8), "elbow")


def test_build_events_sends_date_and_hand_conflicts_to_review():
    tx = pd.DataFrame([
        _tx(1, 10, "T placed RHP P10 on the 15-day injured list. Right shoulder inflammation.",
            "2021-04-16", "2023-04-14"),                                                        # 날짜가 서로 안 맞음
        _tx(2, 11, "T placed RHP P11 on the 15-day injured list. Right elbow sprain."),         # 선수 정보는 좌투
    ])
    people = pd.DataFrame({"id": [10, 11], "pitch_hand": ["R", "L"]})
    ev = lb.build_events(tx, people, RULES)
    assert list(ev["verdict"]) == ["review", "review"]
    assert list(ev["why"]) == ["date_conflict", "hand_mismatch"]


def test_carry_decisions_keeps_what_a_person_already_wrote():
    new = pd.DataFrame({"event_id": [1, 2, 3], "part": ["", "elbow", ""], "decision": ["", "", ""], "note": ["", "", ""]})
    old = pd.DataFrame({"event_id": [2, 9], "part": ["shoulder", ""], "decision": ["제외", "사례"],
                        "note": ["광배근", None]})
    out = lb.carry_decisions(new, old)
    assert list(out["decision"]) == ["", "제외", ""]
    assert list(out["note"]) == ["", "광배근", ""]
    assert list(out["part"]) == ["", "shoulder", ""]         # 사람이 고친 부위도 유지


def test_carry_decisions_also_keeps_suggestions_and_tolerates_older_files_without_them():
    new = pd.DataFrame({"event_id": [1, 2], "part": ["", ""], "suggested": ["", ""], "suggested_note": ["", ""],
                        "decision": ["", ""], "note": ["", ""]})
    with_suggestions = pd.DataFrame({"event_id": [2], "part": [""], "suggested": ["제외"], "suggested_note": ["대원근"],
                                     "decision": [""], "note": [""]})
    out = lb.carry_decisions(new, with_suggestions)
    assert list(out["suggested"]) == ["", "제외"] and list(out["suggested_note"]) == ["", "대원근"]
    older = pd.DataFrame({"event_id": [2], "part": [""], "decision": ["사례"], "note": [""]})
    assert list(lb.carry_decisions(new, older)["decision"]) == ["", "사례"]


def test_parse_accepts_day_counts_written_without_a_hyphen():
    p = parse("Tampa Bay Rays placed RHP Some One on the 60 day injured list. Right elbow inflammation.")
    assert (p["days"], p["reason"]) == (60, "Right elbow inflammation.")       # 2021년 기록 일부의 표기


def _auto():
    return pd.DataFrame({"event_id": [1, 2], "pitcher": [10, 10], "season": [2023, 2023],
                         "il_date": ["2023-08-01", "2023-05-01"], "part": ["elbow", "shoulder"], "description": ["a", "b"]})


def _review(decisions, parts=("elbow", "", "")):
    return pd.DataFrame({"event_id": [3, 4, 5], "pitcher": [11, 12, 10], "name": ["x", "y", "z"],
                         "il_date": ["2023-06-01", "2023-06-02", "2023-04-01"], "description": ["c", "d", "e"],
                         "part": list(parts), "decision": list(decisions), "note": ["", "", ""]})


def test_unreviewed_rows_are_reported_until_every_decision_is_usable():
    assert list(lb.unreviewed(_review(["사례", "", "제외"]))["event_id"]) == [4]          # 빈 줄
    assert list(lb.unreviewed(_review(["사례", "모름", "제외"]))["event_id"]) == [4]      # 정해진 말이 아님
    assert list(lb.unreviewed(_review(["사례", "사례", "제외"]))["event_id"]) == [4]      # 사례인데 부위가 없음
    assert lb.unreviewed(_review(["사례", "제외", "제외"])).empty


def test_final_labels_join_automatic_cases_with_reviewed_cases():
    labels = lb.final_labels(_auto(), _review(["사례", "제외", "제외"]))
    assert sorted(labels["event_id"]) == [1, 2, 3]
    reviewed = labels.set_index("event_id").loc[3]
    assert (reviewed["pitcher"], reviewed["season"], reviewed["part"], reviewed["source"]) == (11, 2023, "elbow", "review")


def test_first_arm_il_keeps_one_event_per_pitcher_season():
    labels = lb.final_labels(_auto(), _review(["사례", "제외", "제외"]))
    cases = lb.first_arm_il(labels)
    assert sorted(cases["event_id"]) == [2, 3]            # 투수 10은 5월(어깨)이 먼저, 8월(팔꿈치)은 빠짐


def test_read_review_accepts_files_saved_by_excel_in_korean_windows_encoding(tmp_path):
    frame = pd.DataFrame({"event_id": [1], "decision": ["사례"], "note": [None]})
    for encoding in ("utf-8-sig", "cp949"):
        path = tmp_path / f"{encoding}.csv"
        frame.to_csv(path, index=False, encoding=encoding)
        got = lb.read_review(path)
        assert got.loc[0, "decision"] == "사례" and got.loc[0, "note"] == ""       # 빈칸은 빈 문자열


def test_carry_decisions_keeps_a_corrected_il_date():
    new = pd.DataFrame({"event_id": [1, 2], "il_date": ["2021-04-16", "2023-06-01"], "part": ["shoulder", "elbow"],
                        "decision": ["", ""], "note": ["", ""]})
    old = pd.DataFrame({"event_id": [1], "il_date": ["2023-04-14"], "part": ["shoulder"], "decision": ["사례"], "note": [""]})
    assert list(lb.carry_decisions(new, old)["il_date"]) == ["2023-04-14", "2023-06-01"]


def test_build_events_keeps_early_2021_placements_worded_as_disabled_list():
    tx = pd.DataFrame([_tx(1, 10, "T placed P P10 on the 10 day disabled list.", "2021-04-01", "2021-04-01")])
    ev = lb.build_events(tx, pd.DataFrame({"id": [10], "pitch_hand": ["R"]}), RULES)
    assert list(ev["event_id"]) == [1]                       # 대조군의 'IL 기록 없음' 확인에 필요한 기록
    assert (ev.iloc[0]["verdict"], ev.iloc[0]["why"], ev.iloc[0]["days"]) == ("exclude", "no_reason", 10)
