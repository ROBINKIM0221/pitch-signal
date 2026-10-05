"""개발셋 실측 보정 테스트 (SPEC 3.9의 2·3). 실행: python -m pytest -q"""
import numpy as np
import pandas as pd

from src.common import calibration as cal
from src.core import stats_core as sc

LAM, T2, H3, H1 = 0.2, 16.27, 10.33, 5.74        # 이론값 (SPEC 표 6): T² 한계, 3개 특징 h, 구속 하나 h


def normal_seasons(n_seasons, n_outings, seed, scale=1.0):
    """정상 상태 투수-시즌들: (u 등판 수×3, 구속만의 uv 등판 수) 목록."""
    rng = np.random.default_rng(seed)
    return [(scale * rng.standard_normal((n_outings, 3)), scale * rng.standard_normal(n_outings))
            for _ in range(n_seasons)]


def test_basic_rule_is_the_core_chart():
    u = 1.3 * np.random.default_rng(0).standard_normal((300, 3))
    alarm = cal.alarms(u, np.zeros(300), cal.Rule(lam=LAM, t2=T2, h=H3))
    assert alarm.sum() > 3 and (alarm == sc.monitor(u, H3, T2, LAM).alarm).all()


def test_union_rule_also_catches_a_velocity_drift_the_multivariate_chart_misses():
    u, uv = np.zeros((12, 3)), np.full(12, 1.5)                      # 구속만 예상보다 계속 1.5만큼 어긋남
    assert not cal.alarms(u, uv, cal.Rule(LAM, T2, H3)).any()
    union = cal.alarms(u, uv, cal.Rule(LAM, T2, H3, h_velo=H1))
    assert list(np.flatnonzero(union)) == [3, 7, 11]                 # 네 등판째에 울리고, 다시 0에서 시작해 반복


def test_union_rule_restarts_both_charts_after_any_alarm():
    u, uv = np.zeros((12, 3)), np.full(12, 1.5)
    u[2] = [5.0, 0.0, 0.0]                                           # 세 번째 등판에서 T² 경보 (25 > 16.27)
    union = cal.alarms(u, uv, cal.Rule(LAM, T2, H3, h_velo=H1))
    assert list(np.flatnonzero(union)) == [2, 6, 10]                 # 구속 EWMA도 함께 0으로 돌아가 3이 아니라 6에서 울림


def test_t2_limit_stays_at_the_theory_value_when_few_outings_exceed_it():
    t2 = np.random.default_rng(1).chisquare(3, 20000)
    assert cal.t2_limit(t2, T2, max_per100=0.5) == T2


def test_t2_limit_rises_until_only_the_allowed_share_exceeds_it():
    t2 = np.arange(1000.0)                                           # 이론 한계 900을 넘는 등판이 9.9%
    limit = cal.t2_limit(t2, 900.0, max_per100=0.5)
    assert limit == 994.0 and 100 * (t2 > limit).mean() == 0.5


def test_fit_basic_brings_false_alarms_down_to_the_target():
    seasons = normal_seasons(200, 40, seed=2, scale=1.15)            # 이론보다 조금 더 흔들리는 실제 데이터 흉내
    rule = cal.fit_basic(seasons, LAM, T2, target=1.0)
    assert 0.9 <= cal.false_alarms_per100(seasons, rule) <= 1.0
    assert cal.false_alarms_per100(seasons, cal.Rule(LAM, T2, H3)) > 1.0 and rule.h > H3
    assert rule.h_velo is None and (rule.lam, rule.t2) == (LAM, T2)


def test_fit_union_balances_the_two_ewma_rules_and_meets_the_target():
    seasons = normal_seasons(100, 40, seed=3)
    rule = cal.fit_union(seasons, LAM, T2, target=1.0, tol=0.05)
    assert 0.8 <= cal.false_alarms_per100(seasons, rule) <= 1.0

    def alone(index, h):          # 그 EWMA 규칙 하나만 썼을 때의 100등판당 경보 수
        return 100 * np.mean(np.concatenate([sc.monitor(s[index], h, np.inf, LAM).alarm for s in seasons]))
    assert abs(alone(0, rule.h) - alone(1, rule.h_velo)) < 0.15
    assert rule.h > cal.fit_basic(seasons, LAM, T2, target=1.0).h    # 규칙이 하나 늘었으니 각 한계는 더 높아야 함


def test_table_alarms_run_one_chart_per_pitcher_season():
    table = pd.DataFrame({"pitcher": [1] * 4 + [2] * 4, "season": 2023, "u_a": 0.0, "uv": [1.5] * 8})
    alarm = cal.table_alarms(table, ["a"], cal.Rule(LAM, T2, H3, h_velo=H1))
    assert list(alarm) == [False, False, False, True] * 2            # 투수가 바뀌면 처음부터 다시 쌓음
    seasons = cal.sequences(table, ["a"])
    assert len(seasons) == 2 and seasons[0][0].shape == (4, 1) and seasons[0][1].shape == (4,)
