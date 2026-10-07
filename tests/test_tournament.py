"""전국체전 변환(가명 처리·입력표·등판 주석) 테스트. 실행: python -m pytest -q tests/test_tournament.py"""
import numpy as np
import pandas as pd

from src.common import highschool as hs
from src.common import tournament as tn

RULES = {"season": 2025, "schools": 3, "competitions": ["전국체전"], "kbsa": {"daily_max": 105, "rest_table": [[45, 0], [60, 1], [75, 2], [90, 3], [105, 4]], "no_three_consecutive_days": True},
         "acwr": {"acute_days": 7, "chronic_days": 21, "flag": 1.5, "min_coverage": 1.0}, "window_days": [3, 7],
         "input_ranges": {"game_no": [1, 999], "pitches": [1, 200], "outs": [0, 60], "team_outs_per_game": [0, 60]}, "foreign_rules": {}}


def raw_rows():
    """세 팀, 세 경기. 2번 경기에서 '다라고' 13번이 두 번 등판하고, 3번 경기는 상세 기록이 없다(모두 0)."""
    rows = [
        (1, "2025-10-17", "가나고", "다라고", "홍길동", 17, "선발", "패", "7", 21, 28, 105),
        (1, "2025-10-17", "다라고", "가나고", "박민수", 54, "선발", "승", "9", 27, 33, 88),
        (2, "2025-10-18", "다라고", "마바고", "박민수", 54, "선발", "-", "1", 3, 4, 12),
        (2, "2025-10-18", "다라고", "마바고", "최지우", 13, "교체", "승", "2.2", 8, 9, 42),
        (2, "2025-10-18", "다라고", "마바고", "최지우", 13, "교체", "-", "1.2", 5, 6, 23),
        (2, "2025-10-18", "마바고", "다라고", "오하늘", 1, "선발", "패", "8", 24, 30, 99),
        (3, "2025-10-22", "가나고", "마바고", "홍길동", 17, "선발", "-", "0", 0, 0, 0),
        (3, "2025-10-22", "마바고", "가나고", "오하늘", 1, "선발", "-", "0", 0, 0, 0),
    ]
    t = pd.DataFrame(rows, columns=["game_idx", "date", "team", "opponent", "name", "number", "role", "result", "innings", "outs", "batters", "pitches"])
    t["date"] = pd.to_datetime(t["date"])
    return t


def test_games_without_detail_get_missing_pitch_counts_not_zero():
    t = tn.mark_missing_detail(raw_rows())
    assert t.loc[t["game_idx"] == 3, "pitches"].isna().all() and not t.loc[t["game_idx"] == 3, "detail"].any()
    assert t.loc[t["game_idx"] != 3, "detail"].all() and t.loc[t["game_idx"] != 3, "pitches"].notna().all()


def test_two_stints_in_one_game_are_combined_into_one_outing():
    t = tn.combine_stints(raw_rows())
    mine = t[(t["game_idx"] == 2) & (t["number"] == 13)]
    assert len(mine) == 1
    row = mine.iloc[0]
    assert row["outs"] == 13 and row["pitches"] == 65 and row["batters"] == 15 and row["role"] == "교체" and row["result"] == "승" and row["stints"] == 2
    assert len(t) == 7 and (t.loc[t["number"] != 13, "stints"] == 1).all()


def test_pseudonyms_are_deterministic_cover_every_school_and_pitcher_and_never_reuse_a_code():
    t = raw_rows()
    names = tn.name_map(t, seed=7)
    assert set(names.columns) == {"team", "name", "number", "school", "pitcher"}
    assert sorted(names["school"].unique()) == ["S01", "S02", "S03"]
    assert names["pitcher"].is_unique and names["pitcher"].str.match(r"^S\d{2}-P\d{2}$").all()
    assert (names["pitcher"].str[:3] == names["school"]).all()
    again = tn.name_map(t, seed=7)
    pd.testing.assert_frame_equal(names, again)


def test_input_rows_follow_the_high_school_input_layout_and_pass_the_input_check():
    t = tn.combine_stints(tn.mark_missing_detail(raw_rows()))
    names = tn.name_map(t, seed=7)
    rows = tn.input_rows(t, names, competition="전국체전", rounds={"16강": 2, "결승": 1})
    for col in ["row", "date", "competition", "game_no", "school", "pitcher", "pitches", "outs", "opponent", "role", "result", "round", "game_idx", "detail"]:
        assert col in rows.columns
    assert rows["game_no"].tolist() == [1, 1, 2, 2, 2, 3, 3] and rows["round"].tolist() == ["16강"] * 5 + ["결승"] * 2
    assert "홍길동" not in rows.to_string() and "가나고" not in rows.to_string()
    assert rows["opponent"].str.match(r"^S\d{2}$").all()
    assert hs.problems(rows, RULES).empty


def test_outing_annotation_gives_rest_gap_requirement_and_cumulative_pitches():
    t = tn.combine_stints(tn.mark_missing_detail(raw_rows()))
    names = tn.name_map(t, seed=7)
    rows = tn.input_rows(t, names, competition="전국체전", rounds={"16강": 2, "결승": 1})
    out = tn.annotate_outings(rows, RULES["kbsa"])
    ace = out[out["pitcher"] == names.set_index("name").loc["박민수", "pitcher"]].sort_values("date")
    assert ace["cum_pitches"].tolist() == [88, 100]
    assert ace["gap_days"].tolist()[1] == 0 and ace["required_rest"].tolist()[1] == 3 and ace["rest_ok"].tolist()[1] is False
    hong = out[out["pitcher"] == names.set_index("name").loc["홍길동", "pitcher"]].sort_values("date")
    assert hong["gap_days"].tolist()[1] == 4 and hong["required_rest"].tolist()[1] == 4 and hong["rest_ok"].tolist()[1] is True and hong["min_rest_exact"].tolist()[1] is True
    assert np.isnan(hong["cum_pitches"].tolist()[1])                     # 투구 수를 모르는 경기 뒤 누적은 모름
    first = out[out["gap_days"].isna()]
    assert len(first) == 4 and first["required_rest"].isna().all() and first["rest_ok"].isna().all()


def test_payload_summarises_each_pitcher_and_the_whole_tournament():
    t = tn.combine_stints(tn.mark_missing_detail(raw_rows()))
    names = tn.name_map(t, seed=7)
    rows = tn.input_rows(t, names, competition="전국체전", rounds={"16강": 2, "결승": 1})
    outings = tn.annotate_outings(rows, RULES["kbsa"])
    daily = hs.daily_table(rows, RULES)
    violated = hs.violations(rows, daily, RULES)
    pay = tn.payload(outings, daily, violated, RULES, {"name": "가상 대회", "short": "전국체전", "season": 2025, "dates": "2025-10-17 ~ 2025-10-22", "source": "시험"})
    assert pay["synthetic"] is False and pay["mode"] == "tournament" and pay["tournament"]["games"] == 3 and pay["tournament"]["no_detail_games"] == [3]
    assert [g["no"] for g in pay["games"]] == [1, 2, 3] and pay["games"][2]["detail"] is False and pay["games"][0]["round"] == "16강"
    code = names.set_index("name").loc["박민수", "pitcher"]
    school = next(s for s in pay["schools"] if s["code"] == code[:3])
    ace = next(p for p in school["pitchers"] if p["code"] == code)
    assert ace["rule_status"] == "위반" and ace["outings"] == 2 and ace["pitches_total"] == 100 and ace["max_pitches"] == 88
    assert ace["games"][1]["rest_ok"] is False and ace["games"][1]["required_rest"] == 3 and ace["games"][1]["gap_days"] == 0
    hong = next(p for s in pay["schools"] for p in s["pitchers"] if p["code"] == names.set_index("name").loc["홍길동", "pitcher"])
    assert hong["rule_status"] == "판정 불가" and hong["pitches_total"] is None and hong["games"][1]["pitches"] is None
    assert pay["totals"]["pitchers"] == 4 and pay["totals"]["outings"] == 7 and pay["totals"]["unknown_outings"] == 2
    assert pay["totals"]["rest_violations"] == 2 and pay["totals"]["back_to_back"] == 1 and pay["totals"]["games_100plus"] == 1   # 99구 뒤 3일 휴식(4일 필요)도 위반
    assert all("days" in p for s in pay["schools"] for p in s["pitchers"])


def test_min_rest_exact_only_counts_outings_after_a_rest_requirement_of_at_least_one_day():
    rows = pd.DataFrame({"row": [2, 3, 4, 5], "date": pd.to_datetime(["2025-10-17", "2025-10-18", "2025-10-20", "2025-10-22"]), "competition": "전국체전",
                         "game_no": [1, 2, 3, 4], "school": "S01", "pitcher": "S01-P01", "pitches": [30.0, 50.0, 10.0, 10.0], "outs": 3})
    out = tn.annotate_outings(rows, RULES["kbsa"])
    # 30구 → 휴식 0일 → 이튿날 등판은 연투이지 '최소 휴식만 채운 등판'이 아니다; 50구 → 1일 → 이틀 뒤 등판은 최소 휴식만 채운 것
    assert out["gap_days"].tolist()[1:] == [0, 1, 1] and out["required_rest"].tolist()[1:] == [0, 1, 0]
    assert out["min_rest_exact"].tolist() == [None, False, True, False] and out["rest_ok"].tolist() == [None, True, True, True]
