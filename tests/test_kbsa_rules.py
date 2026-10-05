"""KBSA 규정 엔진 테스트. 실행: python -m pytest -q"""
import pandas as pd

from src.core import kbsa_rules as kr


def log(rows):
    return pd.DataFrame(rows, columns=["date", "pitches"])


def test_required_rest_table():
    assert [kr.required_rest(p) for p in (45, 46, 60, 61, 75, 76, 90, 91, 105)] == \
           [0, 1, 1, 2, 2, 3, 3, 4, 4]


def test_rest_violation():
    v = kr.check_violations(log([("2026-05-02", 50), ("2026-05-03", 20)]))
    assert list(v.rule) == ["rest"]          # 50구 → 휴식 1일 필요


def test_rest_ok():
    v = kr.check_violations(log([("2026-05-02", 50), ("2026-05-04", 20)]))
    assert v.empty


def test_three_consecutive_days():
    v = kr.check_violations(log([("2026-05-02", 30), ("2026-05-03", 30), ("2026-05-04", 30)]))
    assert list(v.rule) == ["three_days"]     # 45구 이하라 휴식 위반은 아님


def test_daily_max():
    v = kr.check_violations(log([("2026-05-02", 106)]))
    assert list(v.rule) == ["daily_max"]


def test_acwr_values():
    rows = [(f"2026-04-{d:02d}", 30) for d in (1, 8, 15)] + [("2026-04-22", 30), ("2026-04-27", 60)]
    daily = kr.daily_series(log(rows), start="2026-03-31")   # 직전 3주 창이 다 차도록
    a = kr.acwr(daily)
    last = a.iloc[-1]                          # 4/27: 최근 7일 = 4/21~27 → 90구
    assert last.acute == 90
    assert abs(last.chronic - 30.0) < 1e-9     # 3/31~4/20 중 4/1·8·15 = 90구 → 주평균 30
    assert abs(last.acwr - 3.0) < 1e-9


def test_window_limit():
    daily = kr.daily_series(log([("2026-08-01", 110), ("2026-08-03", 105), ("2026-08-05", 100),
                                 ("2026-08-06", 100), ("2026-08-07", 100)]))
    v = kr.window_limit_violations(daily, window_days=7, max_pitches=500)
    assert len(v) == 1 and v.iloc[0].window_sum == 515


def test_missing_pitch_count_is_unknown_not_zero():
    import numpy as np
    v = kr.check_violations(log([("2026-05-02", np.nan), ("2026-05-03", 20)]))
    assert list(v.rule) == ["unknown"]                     # 0구로 보고 '위반 없음' 처리하지 않음
    daily = kr.daily_series(log([("2026-05-01", 30), ("2026-05-02", np.nan)]))
    assert np.isnan(daily.loc["2026-05-02"])
