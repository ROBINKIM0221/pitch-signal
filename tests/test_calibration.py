"""개발셋 실측 보정 테스트 (SPEC 3.8~3.9). 실행: python -m pytest -q"""
import numpy as np
import pandas as pd
import pytest

from src.common import calibration as cal
from src.core import stats_core as sc

LAM, T2, H3, K1 = 0.2, 16.27, 10.33, 2.01        # 이론값: T² 한계, 3개 특징 h, 구속 하락 신호 k (SPEC 3.9)


def normal_seasons(n_seasons, n_outings, seed, scale=1.0):
    """정상 상태 투수-시즌들: (u 등판 수×3, 구속만의 uv 등판 수) 목록."""
    rng = np.random.default_rng(seed)
    return [(scale * rng.standard_normal((n_outings, 3)), scale * rng.standard_normal(n_outings))
            for _ in range(n_seasons)]


def test_change_signal_is_the_core_chart_and_its_index_crosses_one_exactly_at_alarms():
    u = 1.3 * np.random.default_rng(0).standard_normal((300, 3))
    alarm, index = cal.change_signal(u, cal.ChangeRule(LAM, T2, H3))
    assert alarm.sum() > 3 and (alarm == sc.monitor(u, H3, T2, LAM).alarm).all()
    assert (index[alarm] > 1).all() and (index[~alarm] <= 1).all()


def test_velo_signal_fires_only_when_velocity_stays_below_expectation():
    down, up = np.full(12, -1.5), np.full(12, 1.5)
    alarm, index = cal.velo_signal(down, cal.VeloRule(LAM, K1))
    assert list(np.flatnonzero(alarm)) == [2, 5, 8, 11]          # 세 등판째에 넘고, 0에서 다시 시작해 반복
    assert (index[alarm] > 1).all() and index[0] == pytest.approx(0.9 / K1)
    alarm_up, index_up = cal.velo_signal(up, cal.VeloRule(LAM, K1))
    assert not alarm_up.any() and (index_up < 0).all()           # 구속이 올라가면 지수는 음수, 경보 없음


def test_t2_limit_stays_at_the_theory_value_when_few_outings_exceed_it():
    t2 = np.random.default_rng(1).chisquare(3, 20000)
    assert cal.t2_limit(t2, T2, max_per100=0.5) == T2


def test_t2_limit_rises_until_only_the_allowed_share_exceeds_it():
    t2 = np.arange(1000.0)                                        # 이론 한계 900을 넘는 등판이 9.9%
    limit = cal.t2_limit(t2, 900.0, max_per100=0.5)
    assert limit == 994.0 and 100 * (t2 > limit).mean() == 0.5


def test_fit_change_brings_false_alarms_down_to_the_target():
    seasons = [u for u, _ in normal_seasons(200, 40, seed=2, scale=1.15)]
    rule = cal.fit_change(seasons, LAM, T2, target=1.0)
    assert 0.9 <= cal.false_alarms_per100([cal.change_signal(u, rule)[0] for u in seasons]) <= 1.0
    assert rule.h > H3 and (rule.lam, rule.t2) == (LAM, T2)


def test_fit_velo_brings_false_alarms_down_to_the_target():
    calm = [uv for _, uv in normal_seasons(300, 40, seed=3)]
    noisy = [1.2 * uv for uv in calm]
    rule = cal.fit_velo(noisy, LAM, target=1.0)
    assert 0.9 <= cal.false_alarms_per100([cal.velo_signal(uv, rule)[0] for uv in noisy]) <= 1.0
    assert rule.k > cal.fit_velo(calm, LAM, target=1.0).k          # 더 흔들리는 자료일수록 한계가 높아야 함


def test_theory_k_reproduces_the_reference_value():
    assert cal.theory_k(LAM, target=100, n_sim=1500, max_len=800, seed=0) == pytest.approx(K1, abs=0.08)


def test_table_signals_use_each_roles_limits_and_restart_per_pitcher_season():
    table = pd.DataFrame({"pitcher": [1] * 4 + [2] * 4, "season": 2023, "role": ["SP"] * 4 + ["RP"] * 4,
                          "u_a": [0.0] * 8, "uv": [-1.5] * 8})
    rules = {"SP": (cal.VeloRule(LAM, K1), cal.ChangeRule(LAM, T2, H3)),
             "RP": (cal.VeloRule(LAM, 9.0), cal.ChangeRule(LAM, T2, H3))}      # 불펜 한계는 아주 높게
    out = cal.table_signals(table, ["a"], rules)
    assert list(out["velo_alarm"]) == [False, False, True, False] + [False] * 4   # 투수가 바뀌면 처음부터 다시 쌓음
    assert out["velo_index"].iloc[2] > 1 and out["velo_index"].iloc[6] < 1
    assert not out["change_alarm"].any() and (out["change_index"] == 0).all()
    assert len(cal.sequences(table, ["a"])) == 2


def test_final_rules_come_from_the_calibrated_settings():
    cfg = {"monitor": {"final": {"lam": 0.2, "velo": {"SP": {"k": 1.66}, "RP": {"k": 1.70}},
                                 "change": {"SP": {"t2": 21.9, "h": 13.7}, "RP": {"t2": 17.5, "h": 8.25}}}}}
    rules = cal.final_rules(cfg)
    assert rules["SP"] == (cal.VeloRule(0.2, 1.66), cal.ChangeRule(0.2, 21.9, 13.7))
    assert rules["RP"][1].h == 8.25
