"""KBSA 기록 변환(학교 실명·선수 등번호 표기, 입력표, 등판 주석, 대시보드 payload) 테스트. 실행: python -m pytest -q tests/test_hs_records.py"""
import numpy as np
import pandas as pd

from src.common import highschool as hs
from src.common import hs_records as hr

RULES = {"season": 2025, "schools": 3, "competitions": ["전국체전", "주말리그 전반기"], "kbsa": {"daily_max": 105, "rest_table": [[45, 0], [60, 1], [75, 2], [90, 3], [105, 4]], "no_three_consecutive_days": True},
         "acwr": {"acute_days": 7, "chronic_days": 21, "flag": 1.5, "min_coverage": 1.0}, "window_days": [3, 7],
         "input_ranges": {"game_no": [1, 999], "pitches": [1, 200], "outs": [0, 60], "team_outs_per_game": [0, 60]}, "foreign_rules": {}}


def raw_rows():
    """세 팀, 세 경기. 2번 경기에서 '다라고' 13번이 두 번 등판하고, 3번 경기는 상세 기록이 없다(모두 0)."""
    rows = [
        (1, "2025-10-17", "가나고", "다라고", "홍길동", 17, "선발", "패", "7", 21, 28, 105),
        (1, "2025-10-17", "다라고", "가나고", "사아자", 54, "선발", "승", "9", 27, 33, 88),
        (2, "2025-10-18", "다라고", "마바고", "사아자", 54, "선발", "-", "1", 3, 4, 12),
        (2, "2025-10-18", "다라고", "마바고", "차카타", 13, "교체", "승", "2.2", 8, 9, 42),
        (2, "2025-10-18", "다라고", "마바고", "차카타", 13, "교체", "-", "1.2", 5, 6, 23),
        (2, "2025-10-18", "마바고", "다라고", "파하가", 1, "선발", "패", "8", 24, 30, 99),
        (3, "2025-10-22", "가나고", "마바고", "홍길동", 17, "선발", "-", "0", 0, 0, 0),
        (3, "2025-10-22", "마바고", "가나고", "파하가", 1, "선발", "-", "0", 0, 0, 0),
    ]
    t = pd.DataFrame(rows, columns=["game_idx", "date", "team", "opponent", "name", "number", "role", "result", "innings", "outs", "batters", "pitches"])
    t["date"] = pd.to_datetime(t["date"])
    return t


def prepared(competition="전국체전"):
    t = hr.combine_stints(hr.mark_missing_detail(raw_rows()))
    names = hr.name_map(t)
    comp = pd.Series(competition, index=sorted(t["game_idx"].unique()))
    return t, names, hr.input_rows(t, names, comp, rounds={"16강": 2, "결승": 1})


def test_games_without_detail_get_missing_pitch_counts_not_zero():
    t = hr.mark_missing_detail(raw_rows())
    assert t.loc[t["game_idx"] == 3, "pitches"].isna().all() and not t.loc[t["game_idx"] == 3, "detail"].any()
    assert t.loc[t["game_idx"] != 3, "detail"].all() and t.loc[t["game_idx"] != 3, "pitches"].notna().all()


def test_a_zero_pitch_count_with_outs_or_batters_recorded_is_treated_as_unknown():
    t = raw_rows()
    t.loc[(t["game_idx"] == 2) & (t["number"] == 1), "pitches"] = 0          # 8이닝 30타자인데 0구 → 기록 누락
    out = hr.mark_missing_detail(t)
    row = out[(out["game_idx"] == 2) & (out["number"] == 1)].iloc[0]
    assert pd.isna(row["pitches"]) and row["detail"]                          # 경기 자체는 상세 기록이 있다
    assert out.loc[(out["game_idx"] == 2) & (out["number"] == 54), "pitches"].iloc[0] == 12


def test_two_stints_in_one_game_are_combined_into_one_outing():
    t = hr.combine_stints(raw_rows())
    mine = t[(t["game_idx"] == 2) & (t["number"] == 13)]
    assert len(mine) == 1
    row = mine.iloc[0]
    assert row["outs"] == 13 and row["pitches"] == 65 and row["batters"] == 15 and row["role"] == "교체" and row["result"] == "승" and row["stints"] == 2
    assert len(t) == 7 and (t.loc[t["number"] != 13, "stints"] == 1).all()


def test_name_map_keeps_school_names_and_turns_players_into_jersey_number_labels():
    names = hr.name_map(raw_rows())
    assert list(names.columns) == ["team", "name", "number", "school", "pitcher", "label"]
    assert dict(zip(names.drop_duplicates("school")["school"], names.drop_duplicates("school")["team"])) == {"S01": "가나고", "S02": "다라고", "S03": "마바고"}   # 학교 코드는 이름순
    assert names["pitcher"].is_unique and names["pitcher"].str.match(r"^S\d{2}-P\d{2}$").all() and (names["pitcher"].str[:3] == names["school"]).all()
    assert names.set_index("name")["label"].to_dict() == {"홍길동": "#17", "사아자": "#54", "차카타": "#13", "파하가": "#1"}
    pd.testing.assert_frame_equal(names, hr.name_map(raw_rows()))                 # 같은 입력이면 늘 같은 코드


def test_two_players_with_the_same_number_in_one_team_get_distinct_labels():
    t = raw_rows()
    t.loc[t["name"] == "차카타", "number"] = 54                                   # 다라고 54번이 둘
    names = hr.name_map(t)
    labels = names[names["team"] == "다라고"].sort_values("name")["label"].tolist()
    assert labels == ["#54", "#54b"] and names["pitcher"].is_unique


def test_input_rows_follow_the_high_school_input_layout_and_pass_the_input_check():
    t, names, rows = prepared()
    for col in ["row", "date", "competition", "game_no", "school", "pitcher", "pitches", "outs", "opponent", "role", "result", "round", "game_idx", "detail"]:
        assert col in rows.columns
    assert rows["game_no"].tolist() == [1, 1, 2, 2, 2, 3, 3] and rows["round"].tolist() == ["16강"] * 5 + ["결승"] * 2
    assert "홍길동" not in rows.to_string()                                       # 선수 실명은 입력표에 없다
    assert rows["opponent"].isin(["가나고", "다라고", "마바고"]).all()               # 상대는 학교 실명
    assert hs.problems(rows, RULES).empty


def test_competition_can_differ_per_game_and_rounds_are_optional():
    t = hr.combine_stints(hr.mark_missing_detail(raw_rows()))
    comp = pd.Series({1: "주말리그 전반기", 2: "주말리그 전반기", 3: "전국체전"})
    rows = hr.input_rows(t, hr.name_map(t), comp, rounds=None)
    assert rows["competition"].tolist() == ["주말리그 전반기"] * 5 + ["전국체전"] * 2 and rows["round"].isna().all()


def test_outing_annotation_gives_rest_gap_requirement_and_cumulative_pitches():
    t, names, rows = prepared()
    out = hr.annotate_outings(rows, RULES["kbsa"])
    ace = out[out["pitcher"] == names.set_index("name").loc["사아자", "pitcher"]].sort_values("date")
    assert ace["cum_pitches"].tolist() == [88, 100]
    assert ace["gap_days"].tolist()[1] == 0 and ace["required_rest"].tolist()[1] == 3 and ace["rest_ok"].tolist()[1] is False
    hong = out[out["pitcher"] == names.set_index("name").loc["홍길동", "pitcher"]].sort_values("date")
    assert hong["gap_days"].tolist()[1] == 4 and hong["required_rest"].tolist()[1] == 4 and hong["rest_ok"].tolist()[1] is True and hong["min_rest_exact"].tolist()[1] is True
    assert np.isnan(hong["cum_pitches"].tolist()[1])
    first = out[out["gap_days"].isna()]
    assert len(first) == 4 and first["required_rest"].isna().all() and first["rest_ok"].isna().all()


def test_min_rest_exact_only_counts_outings_after_a_rest_requirement_of_at_least_one_day():
    rows = pd.DataFrame({"row": [2, 3, 4, 5], "date": pd.to_datetime(["2025-10-17", "2025-10-18", "2025-10-20", "2025-10-22"]), "competition": "전국체전",
                         "game_no": [1, 2, 3, 4], "school": "S01", "pitcher": "S01-P01", "pitches": [30.0, 50.0, 10.0, 10.0], "outs": 3})
    out = hr.annotate_outings(rows, RULES["kbsa"])
    assert out["gap_days"].tolist()[1:] == [0, 1, 1] and out["required_rest"].tolist()[1:] == [0, 1, 0]
    assert out["min_rest_exact"].tolist() == [None, False, True, False] and out["rest_ok"].tolist() == [None, True, True, True]


def test_tournament_payload_summarises_each_pitcher_and_the_whole_tournament_with_real_school_names():
    t, names, rows = prepared()
    outings = hr.annotate_outings(rows, RULES["kbsa"])
    daily = hs.daily_table(rows, RULES)
    violated = hs.violations(rows, daily, RULES)
    pay = hr.payload(outings, daily, violated, names, RULES, {"mode": "tournament", "name": "가상 대회", "short": "전국체전", "season": 2025, "dates": "2025-10-17 ~ 2025-10-22"}, "시험")
    assert pay["synthetic"] is False and pay["mode"] == "tournament" and pay["dataset"]["games"] == 3 and pay["dataset"]["no_detail_games"] == [3]
    assert [g["no"] for g in pay["games"]] == [1, 2, 3] and pay["games"][2]["detail"] is False and pay["games"][0]["round"] == "16강"
    school = next(s for s in pay["schools"] if s["name"] == "다라고")
    ace = next(p for p in school["pitchers"] if p["label"] == "#54")
    assert ace["rule_status"] == "위반" and ace["outings"] == 2 and ace["pitches_total"] == 100 and ace["max_pitches"] == 88
    assert ace["games"][1]["rest_ok"] is False and ace["games"][1]["opponent"] == "마바고"
    hong = next(p for s in pay["schools"] for p in s["pitchers"] if s["name"] == "가나고" and p["label"] == "#17")
    assert hong["rule_status"] == "판정 불가" and hong["pitches_total"] is None
    assert pay["totals"]["pitchers"] == 4 and pay["totals"]["outings"] == 7 and pay["totals"]["unknown_outings"] == 2
    assert pay["totals"]["rest_violations"] == 2 and pay["totals"]["back_to_back"] == 1 and pay["totals"]["games_100plus"] == 1
    assert pay["totals"]["back_to_back_70"] == 1                                       # 88구 뒤 이튿날 12구 → 이틀 합 100
    assert "홍길동" not in str(pay)                                               # 선수 실명은 payload에 없다


def season_rows():
    """시즌 모드 표본: 한 팀 두 투수, 6주 동안 주말마다 경기. #17은 4주차부터 투구가 급증해 ACWR 1.5를 넘고 의무 휴식도 어긴다."""
    rows = []
    game = 1
    for week in range(6):
        d = pd.Timestamp("2025-03-08") + pd.Timedelta(days=7 * week)
        heavy = 90 if week >= 3 else 30
        rows.append((game, d, "가나고", "다라고", "홍길동", 17, "선발", "-", "5", 15, 20, heavy)); game += 1
        rows.append((game, d + pd.Timedelta(days=1), "가나고", "다라고", "나다라", 23, "선발", "-", "5", 15, 20, 40)); game += 1
        if week >= 3:
            rows.append((game, d + pd.Timedelta(days=1), "가나고", "다라고", "홍길동", 17, "교체", "-", "2", 6, 8, 35)); game += 1
    t = pd.DataFrame(rows, columns=["game_idx", "date", "team", "opponent", "name", "number", "role", "result", "innings", "outs", "batters", "pitches"])
    return t


def test_season_payload_reports_acwr_status_and_the_rule_versus_load_split():
    t = hr.combine_stints(hr.mark_missing_detail(season_rows()))
    names = hr.name_map(t)
    comp = pd.Series("주말리그 전반기", index=sorted(t["game_idx"].unique()))
    rules = {**RULES, "schools": 1}
    rows = hr.input_rows(t, names, comp, rounds=None)
    outings = hr.annotate_outings(rows, rules["kbsa"])
    daily = hs.daily_table(rows, rules)
    violated = hs.violations(rows, daily, rules)
    pay = hr.payload(outings, daily, violated, names, rules, {"mode": "season", "name": "가상 시즌", "short": "시즌", "season": 2025, "region": "경기도"}, "시험")
    assert pay["mode"] == "season" and pay["dataset"]["dates"] == "2025-03-08 ~ 2025-04-13"
    school = pay["schools"][0]
    hong = next(p for p in school["pitchers"] if p["label"] == "#17")
    kim = next(p for p in school["pitchers"] if p["label"] == "#23")
    assert hong["load_status"] == "경보" and hong["acwr_peak"] > 1.5 and kim["load_status"] in ("보통", "주의")
    assert hong["rule_status"] == "위반"                                           # 90구 뒤 이튿날 등판 → 의무 휴식 미준수
    assert any(d["acwr"] is not None for d in hong["days"])
    assert pay["totals"]["acwr_ok_pitchers"] == 2 and pay["totals"]["acwr_flag_pitchers"] == 1
    assert pay["totals"]["compliant_with_flag"] == 0                                  # #17은 위반도 있어서 '규정 지켰지만 부하' 아님
    assert pay["dataset"]["competitions"] == {"주말리그 전반기": 15}
    assert hong["max_7d"] == 125 and kim["max_7d"] == 40                              # 7일 합 최대
    assert pay["totals"]["pitchers_7d_150"] == 0 and pay["totals"]["pitchers_season_500"] == 0 and pay["totals"]["acwr_flag_chronic_median"] > 0
