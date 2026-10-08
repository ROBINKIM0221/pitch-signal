"""KBSA 기록 변환(학교 실명·선수 등번호 표기, 입력표, 등판 주석, 대시보드 payload) 테스트. 실행: python -m pytest -q tests/test_hs_records.py"""
import numpy as np
import pandas as pd

from src.common import highschool as hs
from src.common import hs_records as hr
from src.common import kbsa_boxscore as kb

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
    pay = hr.payload(outings, daily, violated, names, RULES, {"mode": "tournament", "name": "가상 대회", "short": "전국체전", "season": 2025, "dates": "2025-10-17 ~ 2025-10-22"}, "시험", LIGHTS)
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


LIGHTS = {"sum7": {"caution": 120, "high": 150}, "pair3": {"caution": 70, "high": 100}}


def test_season_payload_reports_absolute_load_lights_and_the_rule_versus_load_split():
    t = hr.combine_stints(hr.mark_missing_detail(season_rows()))
    names = hr.name_map(t)
    comp = pd.Series("주말리그 전반기", index=sorted(t["game_idx"].unique()))
    rules = {**RULES, "schools": 1}
    rows = hr.input_rows(t, names, comp, rounds=None)
    outings = hr.annotate_outings(rows, rules["kbsa"])
    daily = hs.daily_table(rows, rules)
    violated = hs.violations(rows, daily, rules)
    pay = hr.payload(outings, daily, violated, names, rules, {"mode": "season", "name": "가상 시즌", "short": "시즌", "season": 2025, "region": "경기도"}, "시험", LIGHTS)
    assert pay["mode"] == "season" and pay["dataset"]["dates"] == "2025-03-08 ~ 2025-04-13" and pay["load_lights"] == LIGHTS
    school = pay["schools"][0]
    hong = next(p for p in school["pitchers"] if p["label"] == "#17")
    kim = next(p for p in school["pitchers"] if p["label"] == "#23")
    # #17: 4주차부터 토 90 + 일 35 → 7일 합 최대 125(주의), 3일 안 두 등판 합 125(높음) → 높음; #23: 주 40 → 보통
    assert hong["max_7d"] == 125 and hong["max_pair3"] == 125 and hong["load_status"] == "높음" and "3일 안 두 등판 합 125구" in " ".join(hong["load_reasons"])
    assert kim["max_7d"] == 40 and kim["max_pair3"] is None and kim["load_status"] == "보통" and kim["load_reasons"] == []
    assert hong["rule_status"] == "위반"                                           # 90구 뒤 이튿날 등판 → 의무 휴식 미준수
    assert "acwr_peak" not in hong and "acwr_flag_pitchers" not in pay["totals"]      # ACWR은 고교 화면에서 쓰지 않는다
    assert pay["totals"]["pitchers_load_high"] == 1 and pay["totals"]["pitchers_load_caution"] == 0 and pay["totals"]["compliant_with_load"] == 0
    assert pay["totals"]["pairs3"] == 3 and pay["totals"]["pairs3_70"] == 3 and pay["totals"]["pairs3_100"] == 3
    assert school["load_high"] == 1 and school["load_caution"] == 0 and school["violations"] == 3 and school["violating_pitchers"] == 1 and school["compliant_with_load"] == 0   # #17이 매주 휴식 위반
    assert school["start"] == "2025-03-08" and school["end"] == "2025-04-13"
    assert pay["dataset"]["competitions"] == {"주말리그 전반기": 15}
    assert pay["totals"]["pitchers_7d_150"] == 0 and pay["totals"]["pitchers_season_500"] == 0


def test_flows_assign_plate_appearances_to_each_pitcher_outing_and_mark_games_that_do_not_add_up():
    from tests.test_kbsa_boxscore import PAGE, BATTING, batting_table
    # 가나고 투수 3명(타자 11·14·7)이 다라고 타자 32명을 상대한 경기: 다라고 타격표는 BATTING(31타석)에 1타석을 더해 32로 맞춘다
    page = PAGE + batting_table("다라고", [(1, "유격수", "가나(7)", {1: "삼진", 3: "중안/4구", 6: "2땅"}), (2, "1루수", "다라(8)", {1: "4구", 3: "사구", 4: "삼진", 7: "유플"}),
                                        (3, "포수", "마바(12)", {1: "우플", 3: "좌월2,폭투", 4: "유땅", 7: "삼진"}), (4, "3루수", "사아(10)", {1: "좌파플", 3: "3실", 4: "중안", 7: "중안"}),
                                        (5, "좌익수", "자차(3)", {2: "삼진", 3: "희플", 5: "병살"}), (6, "우익수", "카타(5)", {2: "2땅", 3: "삼진", 5: "4구"}),
                                        (7, "중견수", "파하(9)", {2: "좌안", 3: "유땅", 5: "좌플", 8: "삼진"}), (8, "2루수", "거너(2)", {2: "1땅", 3: "중안"}),
                                        (8, "대타", "더러(31)", {6: "삼진"}), (9, "지명타자", "머버(1)", {2: "삼진", 3: "좌플", 6: "삼진"})])
    game = kb.parse_record_detail(page, game_idx=1)
    flows = hr.flows_for_game(game, kb.parse_batting(page))
    assert set(flows) == {("가나고", "홍길동", 17), ("가나고", "나다라", 23), ("가나고", "마바사", 11)}
    first = flows[("가나고", "홍길동", 17)]
    assert len(first) == 11 and first[0] == {"inn": 1, "res": "삼진", "cat": "K", "ev": []} and first[-1]["inn"] == 3
    assert len(flows[("가나고", "나다라", 23)]) == 14 and len(flows[("가나고", "마바사", 11)]) == 7
    assert flows[("가나고", "마바사", 11)][-1] == {"inn": 8, "res": "삼진", "cat": "K", "ev": []}
    assert hr.flows_for_game(game, {}) == {}                                               # 상대 타격표가 없으면 흐름 없음
    short = kb.parse_batting(page); short["다라고"] = short["다라고"][:-1]                    # 타석 수가 안 맞으면 그 팀 투수들은 흐름 없음
    assert hr.flows_for_game(game, short) == {}


def test_flow_summary_counts_categories_and_walk_heavy_innings():
    flow = [{"inn": 1, "res": "4구", "cat": "BB", "ev": []}, {"inn": 1, "res": "사구", "cat": "HBP", "ev": []}, {"inn": 1, "res": "삼진", "cat": "K", "ev": []},
            {"inn": 2, "res": "중안", "cat": "H", "ev": ["폭투"]}, {"inn": 2, "res": "좌월홈", "cat": "HR", "ev": []}, {"inn": 2, "res": "2땅", "cat": "OUT", "ev": []}]
    assert hr.flow_summary(flow) == {"pa": 6, "k": 1, "bb": 1, "hbp": 1, "h": 2, "hr": 1, "walk_innings": [1], "wild": 1}


def sheet_outings():
    """기록지 판독 결과(경기·던진 팀·등번호): 1경기 다라고 #54 읽음·통과, 가나고 #17 읽었지만 검산 미달, 2경기 다라고 #13 통과·'평소보다 볼 많음'."""
    return pd.DataFrame({"game_idx": [1, 1, 2], "team": ["다라고", "가나고", "다라고"], "number": [54, 17, 13], "pitches": [88, 105, 65],
                         "marks": [80, 70, 60], "balls": [30, 25, 27], "gate": [True, False, True], "ball_pct": [0.375, np.nan, 0.45],
                         "usual": [np.nan, np.nan, 0.35], "z_ball": [np.nan, np.nan, 2.4], "ball_flag": [False, False, True]})


def test_attach_scoresheet_keeps_read_failed_and_unread_apart():
    t, names, rows = prepared()
    out = hr.attach_scoresheet(rows, sheet_outings(), names).set_index(["game_idx", "pitcher"])
    assert out.loc[(1, "S02-P02"), "ball_pct"] == 0.375 and out.loc[(1, "S02-P02"), "ball_marks"] == 80
    assert np.isnan(out.loc[(1, "S01-P01"), "ball_pct"]) and out.loc[(1, "S01-P01"), "ball_marks"] == 70     # 읽었지만 검산 미달 → 비율 없음
    assert bool(out.loc[(2, "S02-P01"), "ball_flag"]) and out.loc[(2, "S02-P01"), "ball_balls"] == 27
    assert np.isnan(out.loc[(2, "S03-P01"), "ball_marks"])                                               # 기록지를 안 읽은 등판
    assert len(out) == len(rows)


def test_payload_carries_ball_rates_per_game_and_pooled_per_pitcher():
    t, names, rows = prepared()
    outings = hr.annotate_outings(hr.attach_scoresheet(rows, sheet_outings(), names), RULES["kbsa"])
    daily = hs.daily_table(rows, RULES); violated = hs.violations(rows, daily, RULES)
    pay = hr.payload(outings, daily, violated, names, RULES, {"mode": "tournament", "name": "가상 대회", "short": "전국체전", "season": 2025, "dates": "-"}, "시험", LIGHTS)
    school = next(s for s in pay["schools"] if s["name"] == "다라고")
    ace = next(p for p in school["pitchers"] if p["label"] == "#54")
    reliever = next(p for p in school["pitchers"] if p["label"] == "#13")
    assert ace["games"][0]["ball_pct"] == 0.375 and ace["games"][0]["ball_marks"] == 80 and ace["games"][1]["ball_marks"] is None
    assert ace["ball_season"] == 0.375 and ace["ball_outings"] == 1 and ace["ball_flags"] == 0
    assert reliever["games"][0]["ball_flag"] is True and reliever["ball_flags"] == 1 and abs(reliever["ball_season"] - 0.45) < 1e-9
    hong = next(p for s in pay["schools"] for p in s["pitchers"] if s["name"] == "가나고")
    assert hong["ball_season"] is None and hong["ball_outings"] == 0 and hong["games"][0]["ball_marks"] == 70
    assert pay["totals"]["ball_outings"] == 2 and pay["totals"]["ball_flags"] == 1


def test_reread_share_rides_along_to_each_game_when_the_reader_reports_it():
    t, names, rows = prepared()
    sheet = sheet_outings().assign(reread=[0.0, 0.0, 0.4])                 # 2경기 다라고 #13: 표시의 40%를 다시 읽음
    outings = hr.annotate_outings(hr.attach_scoresheet(rows, sheet, names), RULES["kbsa"])
    daily = hs.daily_table(rows, RULES); violated = hs.violations(rows, daily, RULES)
    pay = hr.payload(outings, daily, violated, names, RULES, {"mode": "tournament", "name": "가상 대회", "short": "전국체전", "season": 2025, "dates": "-"}, "시험", LIGHTS)
    school = next(s for s in pay["schools"] if s["name"] == "다라고")
    reliever = next(p for p in school["pitchers"] if p["label"] == "#13")
    ace = next(p for p in school["pitchers"] if p["label"] == "#54")
    assert reliever["games"][0]["ball_reread"] == 0.4 and ace["games"][0]["ball_reread"] == 0.0
    plain = hr.attach_scoresheet(rows, sheet_outings(), names)                # 옛 판독 결과(열 없음)도 그대로 붙는다
    assert "ball_reread" not in plain.columns


def test_with_player_names_prefixes_label_with_real_name_for_that_dataset_only():
    names = pd.DataFrame({"pitcher": ["S01-P01", "S01-P02", "S02-P01"], "label": ["#1", "#17", "#17-2"], "team": ["가나고"] * 2 + ["다라고"]})
    real = pd.DataFrame({"pitcher": ["S01-P01", "S01-P02", "S01-P01"], "name": ["홍길동", "김철수", "다른대회"],
                         "dataset": ["korea_2025", "korea_2025", "tournament_2025"]})
    out = hr.with_player_names(names, real, "korea_2025")
    assert out["label"].tolist() == ["홍길동 #1", "김철수 #17", "#17-2"]          # 대응표에 없으면 등번호 그대로
    assert names["label"].tolist() == ["#1", "#17", "#17-2"]                       # 원본 표는 바꾸지 않는다


def inning_rows():
    """기록지 투구수 줄 판독(경기·던진 팀·등번호·이닝): 1경기 다라고 #54는 이닝 합 88 = 공식, 2경기 다라고 #13은 합 60 ≠ 공식 65(42+23)."""
    return pd.DataFrame({"game_idx": [1, 1, 1, 2, 2], "team": ["다라고"] * 5, "number": [54, 54, 54, 13, 13], "inning": [1, 2, 3, 6, 7],
                         "pitches": [30, 40, 18, 30, 30], "shared": [False, False, True, False, False], "marks": [29, 38, 15, 30, 30],
                         "balls": [11, 15, None, 12, 10], "strikes": [19, 25, None, 18, 20]})


def test_attach_innings_adds_per_inning_list_only_when_it_adds_up_to_the_official_count():
    t, names, rows = prepared()
    out = hr.attach_innings(rows, inning_rows(), names).set_index(["game_idx", "pitcher"])
    assert out.loc[(1, "S02-P02"), "innings"] == [[1, 30, 19, 11, False], [2, 40, 25, 15, False], [3, 18, None, None, True]]
    assert out.loc[(2, "S02-P01"), "innings"] is None             # 이닝 합 60 ≠ 공식 65 → 붙이지 않는다
    assert out.loc[(1, "S01-P01"), "innings"] is None             # 판독 없음
    assert len(out) == len(rows)


def test_payload_carries_innings_per_game():
    t, names, rows = prepared()
    outings = hr.annotate_outings(hr.attach_innings(rows, inning_rows(), names), RULES["kbsa"])
    daily = hs.daily_table(rows, RULES); violated = hs.violations(rows, daily, RULES)
    pay = hr.payload(outings, daily, violated, names, RULES, {"mode": "tournament", "name": "가상 대회", "short": "전국체전", "season": 2025, "dates": "-"}, "시험", LIGHTS)
    ace = next(p for s in pay["schools"] for p in s["pitchers"] if s["name"] == "다라고" and p["label"] == "#54")
    assert ace["games"][0]["innings"][0] == [1, 30, 19, 11, False] and ace["games"][1]["innings"] is None
