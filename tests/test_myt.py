"""경보 원인 분해 테스트 (SPEC 3.10). 실행: python -m pytest -q"""
import numpy as np
import pytest

from src.common import myt
from src.core import stats_core as sc

NAMES = ["velo", "rel_z", "arm_angle"]


def test_step_terms_add_up_to_t2():
    rng = np.random.default_rng(0)
    a = rng.standard_normal((3, 3))
    cov, d = a @ a.T + np.eye(3), 2 * rng.standard_normal(3)
    parts = myt.decompose(d + 5.0, np.full(3, 5.0), cov, NAMES)
    assert list(parts.index) == NAMES
    assert parts["step"].sum() == pytest.approx(d @ np.linalg.inv(cov) @ d)
    assert np.allclose(parts["z"], d / np.sqrt(np.diag(cov)))            # 부호 있는 표준화 이탈
    assert parts["step"].max() == pytest.approx(parts["alone"].max())    # 혼자서 가장 크게 벗어난 특징부터 뗀다


def test_uncorrelated_features_contribute_their_own_squared_deviation():
    parts = myt.decompose(np.array([-1.2, -1.8, 0.3]), np.zeros(3), np.eye(3), NAMES)
    for column in ("alone", "given_rest", "step"):
        assert np.allclose(parts[column], [1.44, 3.24, 0.09])


def test_conditional_term_exposes_a_deviation_that_breaks_the_usual_correlation():
    cov = np.array([[1.0, 0.9], [0.9, 1.0]])                 # 평소에는 함께 움직이는 두 특징이 반대로 벗어남
    parts = myt.decompose(np.array([1.0, -1.0]), np.zeros(2), cov, ["velo", "rel_z"])
    assert np.allclose(parts["alone"], [1.0, 1.0])            # 따로 보면 1σ씩이라 평범함
    assert np.allclose(parts["given_rest"], [19.0, 19.0])     # 다른 특징을 알고 보면 크게 벗어남
    assert np.allclose(parts["step"], [1.0, 19.0])


def test_card_names_the_two_largest_contributors_with_signed_sigmas():
    parts = myt.decompose(np.array([-1.2, -1.8, 0.3]), np.zeros(3), np.eye(3), NAMES)
    assert myt.card(parts) == "수직 릴리스 −1.8σ, 구속 −1.2σ"
    assert myt.card(myt.decompose(np.array([2.0, 0.0, 0.5]), np.zeros(3), np.eye(3), NAMES), top=1) == "구속 +2.0σ"


def test_ewma_vectors_match_the_chart_including_restarts_after_alarms():
    u = 1.6 * np.random.default_rng(1).standard_normal((60, 3))
    chart = sc.monitor(u, h=10.33, ucl=16.27, lam=0.2)
    z = myt.ewma_vectors(u, chart.alarm, 0.2)
    assert chart.alarm.sum() >= 2
    assert np.allclose((2 - 0.2) / 0.2 * (z ** 2).sum(axis=1), chart.q)
