"""사례·대조군 확정 테스트 (SPEC 3.13.2). 실행: python -m pytest -q"""
import pandas as pd

from src.common import cases as cs

RULES = {"window_outings": 5, "min_post_baseline_outings": 5, "controls_per_case": 2, "age_tolerance": 2,
         "control_il_free_days": 30, "exclude_missing_tracking_frac": 0.20,
         "max_days_last_outing_to_index": 15, "max_gap_in_window_days": 30}
NO_IL = pd.DataFrame({"pitcher": [], "il_date": pd.to_datetime([])})


def season(pitcher, role="SP", n_baseline=8, n_monitor=6, start="2023-04-01", step=5, n_all=90, missing=0.0):
    """한 투수-시즌의 등판 표: 시작 구간 n_baseline개 + 감시 n_monitor개, step일 간격."""
    n = n_baseline + n_monitor
    return pd.DataFrame({
        "pitcher": pitcher, "season": 2023, "role": role, "game_pk": [pitcher * 100 + i for i in range(n)],
        "game_date": pd.date_range(start, periods=n, freq=f"{step}D"), "n_all": n_all,
        "phase": ["baseline"] * n_baseline + ["monitor"] * n_monitor, "core_missing_frac": missing})


def people(ages):
    return pd.DataFrame({"id": list(ages), "birth_date": [f"{2023 - a}-01-01" for a in ages.values()]})


def arm_il(*pitchers):
    """그 시즌에 팔 부상 IL이 있어 대조군이 될 수 없는 투수-시즌."""
    return pd.DataFrame({"pitcher": list(pitchers), "season": 2023})


def one_case(**changes):
    case = {"case_id": 1, "pitcher": 1, "season": 2023, "role": "SP", "part": "elbow",
            "il_date": pd.Timestamp("2023-06-01"), "age": 28.4, "cum_pitches": 1170}
    return pd.DataFrame([{**case, **changes}])


def test_window_is_the_last_five_monitored_outings_before_the_index_date():
    o = season(1)                                     # 감시 등판 날짜: 5/11, 5/16, 5/21, 5/26, 5/31, 6/5
    games, why = cs.window(o, pd.Timestamp("2023-06-01"), RULES)
    assert games == [108, 109, 110, 111, 112] and why == ""          # 6/5 등판은 기준일 뒤라 빠짐


def test_window_needs_enough_monitored_outings():
    games, why = cs.window(season(1, n_monitor=4), pd.Timestamp("2023-07-01"), RULES)
    assert games is None and why == "감시 등판 부족"


def test_window_rejects_a_pitcher_who_was_not_pitching_just_before_the_index_date():
    games, why = cs.window(season(1), pd.Timestamp("2023-07-15"), RULES)        # 마지막 등판 6/5에서 40일 뒤
    assert games is None and why == "기준일 직전 등판 없음"


def test_window_rejects_a_long_break_inside_the_window():
    o = season(1)
    o.loc[o.index[-3:], "game_date"] += pd.Timedelta(days=40)                    # 창 안에 45일 공백
    games, why = cs.window(o, o["game_date"].max() + pd.Timedelta(days=1), RULES)
    assert games is None and why == "관찰 창 안 공백"


def test_build_cases_keeps_usable_cases_with_age_and_workload():
    outings = pd.concat([season(1), season(2, n_monitor=3), season(3, missing=0.5)])
    raw = pd.DataFrame({"event_id": [11, 12, 13, 14], "pitcher": [1, 2, 3, 4], "season": 2023,
                        "part": ["elbow", "shoulder", "elbow", "elbow"], "il_date": ["2023-06-01"] * 4})   # 4번은 등판 없음
    kept, dropped = cs.build_cases(raw, outings, people({1: 28, 2: 30, 3: 25, 4: 31}), RULES)
    assert list(kept["pitcher"]) == [1]
    row = kept.iloc[0]
    assert (row["case_id"], row["role"], row["part"], row["cum_pitches"]) == (11, "SP", "elbow", 13 * 90)   # 기준일 전 13등판
    assert row["il_date"] == pd.Timestamp("2023-06-01") and 28.3 < row["age"] < 28.5
    assert row["window_games"] == [108, 109, 110, 111, 112]
    assert dict(zip(dropped["pitcher"], dropped["why"])) == {2: "감시 등판 부족", 3: "트래킹 결측 과다", 4: "감시 등판 부족"}


def test_controls_are_the_closest_workloads_among_similar_healthy_pitchers():
    outings = pd.concat([season(1), season(2, n_all=85), season(3, n_all=60), season(4, n_all=93),
                         season(5, n_all=91, role="RP"), season(6, n_all=89), season(7, n_all=92)])
    il = pd.DataFrame({"pitcher": [7], "il_date": pd.to_datetime(["2023-06-20"])})       # 7번은 기준일 19일 뒤 IL
    ages = people({1: 28, 2: 29, 3: 28, 4: 27, 5: 28, 6: 33, 7: 28})                     # 6번은 다섯 살 많음
    controls = cs.match_controls(one_case(), outings, il, arm_il(1), ages, RULES)
    assert list(controls["pitcher"]) == [4, 2]              # 6·7번이 더 가깝지만 나이·IL로 빠지고, 3번(390 차이)은 밀림
    assert list(controls["dist"]) == [39, 65] and set(controls["case_id"]) == {1}
    assert list(controls["index_date"]) == [pd.Timestamp("2023-06-01")] * 2
    assert controls.iloc[0]["window_games"] == [408, 409, 410, 411, 412]
    assert 27.3 < controls.iloc[0]["age"] < 27.5 and controls.iloc[0]["cum_pitches"] == 13 * 93


def test_equal_distances_are_ordered_by_pitcher_id():
    outings = pd.concat([season(1), season(9), season(3), season(2)])
    controls = cs.match_controls(one_case(), outings, NO_IL, arm_il(1), people({1: 28, 2: 28, 3: 28, 9: 28}), RULES)
    assert list(controls["pitcher"]) == [2, 3]


def test_a_pitcher_season_serves_as_a_control_only_once():
    outings = pd.concat([season(1), season(2), season(3), season(8)])
    cases = pd.concat([one_case(), one_case(case_id=2, pitcher=8)])
    controls = cs.match_controls(cases, outings, NO_IL, arm_il(1, 8), people({1: 28, 2: 28, 3: 28, 8: 28}), RULES)
    assert list(controls[controls["case_id"] == 1]["pitcher"]) == [2, 3]
    assert controls[controls["case_id"] == 2].empty                   # 2·3번은 이미 썼고 1번은 팔 부상 IL이 있는 시즌


def test_pitchers_with_an_arm_injury_that_season_are_not_controls():
    outings = pd.concat([season(1), season(2), season(3)])
    controls = cs.match_controls(one_case(), outings, NO_IL, arm_il(1, 2), people({1: 28, 2: 28, 3: 28}), RULES)
    assert list(controls["pitcher"]) == [3]


def test_controls_follow_the_same_window_and_tracking_rules_as_cases():
    outings = pd.concat([season(1), season(2, n_monitor=4),                 # 감시 등판 4개
                         season(3, missing=0.5),                            # 트래킹 결측 과다
                         season(4, n_all=60),
                         season(6, start="2023-02-15")])                    # 마지막 등판이 4/21, 기준일 41일 전
    ages = people({1: 28, 2: 28, 3: 28, 4: 28, 6: 28})
    controls = cs.match_controls(one_case(), outings, NO_IL, arm_il(1), ages, RULES)
    assert list(controls["pitcher"]) == [4]                 # 조건을 지키는 투수가 한 명뿐이면 한 명만


def test_window_table_lists_one_window_outing_per_row():
    controls = pd.DataFrame([{"case_id": 1, "pitcher": 4, "season": 2023, "window_games": [408, 409]}])
    table = cs.window_table(one_case(window_games=[108, 109]), controls)
    assert table.to_dict("list") == {"case_id": [1, 1, 1, 1], "group": ["case", "case", "control", "control"],
                                     "pitcher": [1, 1, 4, 4], "season": [2023] * 4, "game_pk": [108, 109, 408, 409]}


def test_count_table_counts_cases_and_controls_by_season_and_split():
    cases = pd.DataFrame({"case_id": [1, 2, 3], "season": [2023, 2023, 2024], "role": ["SP", "RP", "RP"],
                          "part": ["elbow", "shoulder", "elbow"]})
    controls = pd.DataFrame({"case_id": [1, 1, 3]})
    table = cs.count_table(cases, controls, {"dev": [2021, 2022, 2023], "val": [2024, 2025], "sealed": [2026]})
    assert list(table.index) == ["2023", "2024", "개발 합계", "검증 합계"]
    assert table.loc["2023"].to_dict() == {"사례": 2, "선발": 1, "불펜": 1, "팔꿈치": 1, "어깨": 1, "대조군": 2,
                                           "대조군 1명뿐": 0, "대조군 없음": 1}
    assert table.loc["개발 합계"].tolist() == table.loc["2023"].tolist()
    assert table.loc["검증 합계", ["사례", "대조군", "대조군 1명뿐", "대조군 없음"]].tolist() == [1, 1, 1, 0]
