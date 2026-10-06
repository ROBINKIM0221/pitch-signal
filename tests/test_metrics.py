"""평가 지표 테스트 (SPEC 3.13.3~3.13.4). 실행: python -m pytest -q"""
import numpy as np
import pandas as pd
import pytest

from src.common import metrics as mt


def windows(*groups):
    """(case_id, group, pitcher, game_pk 목록)들로 관찰 창 표를 만든다."""
    rows = [{"case_id": c, "group": g, "pitcher": p, "season": 2023, "game_pk": k} for c, g, p, games in groups for k in games]
    return pd.DataFrame(rows)


def monitored(pitcher, games, alarms):
    return pd.DataFrame({"pitcher": pitcher, "season": 2023, "game_pk": games,
                         "game_date": pd.date_range("2023-05-01", periods=len(games), freq="5D"), "alarm": alarms})


def test_window_results_report_whether_and_how_early_an_alarm_rang():
    table = pd.concat([monitored(1, [10, 11, 12, 13, 14, 15], [True, False, True, False, True, False]),
                       monitored(2, [21, 22, 23, 24, 25], [False] * 5)])
    w = windows((1, "case", 1, [15, 14, 13, 12, 11]), (1, "control", 2, [21, 22, 23, 24, 25]))      # 순서가 뒤섞여 있어도 됨
    out = mt.window_results(w, table).set_index("group")
    assert out.loc["case", "hit"] and out.loc["case", "lead"] == 4       # 창 밖(10)의 경보는 세지 않고, 12·13·14·15 네 등판
    assert not out.loc["control", "hit"] and np.isnan(out.loc["control", "lead"])
    assert out.loc["case", "case_id"] == 1 and out.loc["control", "pitcher"] == 2


def test_window_results_refuse_window_outings_that_were_not_monitored():
    w = windows((1, "case", 1, [11, 99]))
    with pytest.raises(ValueError, match="감시 결과에 없는"):
        mt.window_results(w, monitored(1, [11], [False]))


def test_detection_summary_counts_cases_only():
    results = pd.DataFrame({"case_id": [1, 1, 2, 2, 3], "group": ["case", "control", "case", "control", "case"],
                            "hit": [True, True, False, False, True], "lead": [4, 1, np.nan, np.nan, 1]})
    s = mt.detection(results)
    assert s == {"cases": 3, "detected": 2, "detection_rate": 2 / 3, "median_lead": 2.5,
                 "controls": 2, "control_window_rate": 0.5}


def test_window_results_can_read_named_alarm_and_index_columns():
    table = pd.concat([monitored(1, [11, 12, 13], [False, True, False]), monitored(2, [21, 22, 23], [False] * 3)])
    table = table.rename(columns={"alarm": "velo_alarm"}).assign(velo_index=[0.2, 1.4, 0.3, -0.5, 0.1, 0.0])
    w = windows((1, "case", 1, [11, 12, 13]), (1, "control", 2, [21, 22, 23]))
    out = mt.window_results(w, table, alarm="velo_alarm", index="velo_index").set_index("group")
    assert out.loc["case", "hit"] and out.loc["case", "top"] == 1.4          # 창 지수 = 창 안 지수의 최댓값
    assert not out.loc["control", "hit"] and out.loc["control", "top"] == 0.1


def test_concordance_is_the_share_of_controls_the_case_beats():
    results = pd.DataFrame({"case_id": [1, 1, 1, 2, 2, 2, 3, 3], "group": ["case", "control", "control"] * 2 + ["case", "control"],
                            "top": [1.0, 0.5, 1.0, 0.2, 0.8, 0.9, 2.0, 0.1]})
    per_case = mt.concordance(results)
    assert per_case.to_dict() == {1: 0.75, 2: 0.0, 3: 1.0}      # 1번: 이김 1 + 비김 0.5 → 0.75


def test_concordance_skips_cases_without_controls():
    results = pd.DataFrame({"case_id": [1, 2, 2], "group": ["case", "case", "control"], "top": [1.0, 0.3, 0.1]})
    assert mt.concordance(results).to_dict() == {2: 1.0}


def test_bootstrap_ci_brackets_the_mean_and_is_reproducible():
    values = pd.Series(np.random.default_rng(0).normal(0.6, 0.3, 150))
    mean, lo, hi = mt.bootstrap_ci(values, reps=500, seed=1)
    assert mean == pytest.approx(values.mean()) and lo < mean < hi and hi - lo < 0.15
    assert (mean, lo, hi) == mt.bootstrap_ci(values, reps=500, seed=1)
