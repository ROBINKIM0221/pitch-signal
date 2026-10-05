"""불펜 부하 채널 지표 테스트 (SPEC 3.11). 실행: python -m pytest -q"""
import numpy as np
import pandas as pd

from src.common import load as ld

RULES = {"acute_days": 7, "chronic_days": 21, "consecutive_days_flag": 3, "apps_3d_flag": 3, "p7d_percentile": 95,
         "acwr_flag": 1.5, "long_outing_pitches": 30, "short_rest_days": 1}


def log(rows):
    return pd.DataFrame([{"game_pk": i, "game_date": pd.Timestamp(d), "n_all": n} for i, (d, n) in enumerate(rows)])


def metrics(rows, baseline_end=None):
    end = pd.Timestamp(baseline_end) if baseline_end else pd.NaT
    return ld.load_metrics(log(rows), RULES, end).set_index("game_date")


def test_back_to_back_streak_and_recent_appearances():
    m = metrics([("2023-04-01", 20), ("2023-04-02", 15), ("2023-04-03", 10), ("2023-04-06", 35), ("2023-04-07", 5)])
    assert list(m["back_to_back"]) == [False, True, True, False, True]
    assert list(m["consecutive_days"]) == [1, 2, 3, 1, 2]
    assert list(m["apps_3d"]) == [1, 2, 3, 1, 2]
    assert list(m["flag_consecutive"]) == [False, False, True, False, False]
    assert list(m["flag_apps_3d"]) == [False, False, True, False, False]


def test_seven_day_pitches_previous_outing_and_rest():
    m = metrics([("2023-04-01", 20), ("2023-04-02", 15), ("2023-04-03", 10), ("2023-04-06", 35), ("2023-04-07", 5)])
    assert list(m["p7d"]) == [20, 35, 45, 80, 85]
    assert np.isnan(m["prev_pitches"].iloc[0]) and list(m["prev_pitches"].iloc[1:]) == [20, 15, 10, 35]
    assert list(m["rest_days"].iloc[1:]) == [0, 0, 2, 0]
    assert list(m["flag_long_short"]) == [False, False, False, False, True]      # 35구 다음 날 등판


def test_acwr_compares_last_week_with_the_three_weeks_before():
    m = metrics([("2023-04-01", 30), ("2023-04-08", 30), ("2023-04-15", 30), ("2023-04-22", 30), ("2023-04-29", 60)])
    assert m["acwr"].iloc[:4].isna().all()                  # 직전 3주가 다 차기 전에는 계산하지 않음
    assert m["acwr"].iloc[4] == 2.0                         # 60 ÷ (90 / 3)
    assert list(m["flag_acwr"]) == [False, False, False, False, True]


def test_same_day_outings_are_added_together():
    m = ld.load_metrics(log([("2023-04-01", 10), ("2023-04-01", 12), ("2023-04-02", 5)]), RULES, pd.NaT)
    assert list(m["p7d"]) == [22, 22, 27]
    assert list(m["apps_3d"]) == [2, 2, 3]


def test_seven_day_flag_uses_the_pitchers_own_baseline_percentile():
    rows = [(f"2023-04-{d:02d}", 10) for d in (1, 5, 9, 13, 17)] + [("2023-05-01", 10), ("2023-05-02", 25)]
    m = metrics(rows, baseline_end="2023-04-17")
    assert list(m["flag_p7d"]) == [False] * 6 + [True]      # 기준선 기간의 7일 합(최대 20)을 넘는 35구
    assert not metrics(rows)["flag_p7d"].any()              # 기준선이 없으면 표시하지 않음


def test_flag_rates_count_outings_after_the_baseline_of_the_chosen_pitcher_seasons():
    load = pd.DataFrame({
        "pitcher": [1, 1, 1, 1, 2, 2, 3], "season": 2023,
        "game_date": pd.to_datetime(["2023-04-01", "2023-05-01", "2023-05-02", "2023-05-03",
                                     "2023-05-01", "2023-05-02", "2023-05-01"]),
        "flag_acwr": [True, True, False, False, True, True, True],
        "flag_apps_3d": [True, False, False, True, False, False, True]})
    ends = pd.Series(pd.to_datetime(["2023-04-15", "2023-05-01", "2023-04-15"]),
                     index=pd.MultiIndex.from_tuples([(1, 2023), (2, 2023), (3, 2023)], names=["pitcher", "season"]))
    rates = ld.flag_rates(load, pd.DataFrame({"pitcher": [1, 2], "season": 2023}), ends)     # 3번 투수는 고르지 않음
    assert rates.loc["flag_acwr"].to_dict() == {"outings": 4, "flagged": 2, "rate": 0.5}     # 1번의 5월 3등판 + 2번의 5/2
    assert rates.loc["flag_apps_3d"].to_dict() == {"outings": 4, "flagged": 1, "rate": 0.25}
