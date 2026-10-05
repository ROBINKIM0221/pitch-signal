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
