"""핵심 통계 함수 테스트. 실행: python -m pytest -q"""
import numpy as np

from src.core import stats_core as sc

RNG = np.random.default_rng(42)
P = 3
SB_TRUE = np.diag([0.25, 0.30, 0.20])
SW_TRUE = np.eye(P)


def make_outings(m, n_lo=3, n_hi=14, shift=None, rng=RNG):
    outs = []
    for _ in range(m):
        n = int(rng.integers(n_lo, n_hi))
        day = rng.multivariate_normal(np.zeros(P), SB_TRUE)
        x = day + rng.multivariate_normal(np.zeros(P), SW_TRUE, size=n)
        if shift is not None:
            x = x + shift
        outs.append(x)
    return outs


def test_phase1_recovers_components():
    base = sc.phase1(make_outings(600))
    assert np.allclose(np.diag(base.Sw), 1.0, atol=0.08)
    assert np.allclose(np.diag(base.Sb), np.diag(SB_TRUE), atol=0.08)


def test_u_is_standard_normal_for_any_outing_length():
    base = sc.phase1(make_outings(600))
    new = make_outings(6000)
    U = np.array([sc.outing_u(o.mean(0), len(o), base) for o in new])
    ns = np.array([len(o) for o in new])
    for lo, hi in [(3, 5), (6, 9), (10, 13)]:
        v = U[(ns >= lo) & (ns <= hi)].var(0)
        assert np.all(np.abs(v - 1) < 0.15), (lo, hi, v)


def test_calibrated_h_gives_target_arl0():
    ucl = sc.t2_ucl(P, 0.001)
    h = sc.calibrate_h(P, 0.2, ucl, target=100, n_sim=2000, max_len=1200, seed=0)
    a = sc.arl0(h, P, 0.2, ucl, n_sim=3000, max_len=1200, seed=99)
    assert 88 <= a <= 112, (h, a)


def test_monitor_resets_after_alarm():
    U = np.zeros((6, P))
    U[1] = 10.0                      # 큰 이탈 → T² 경보
    r = sc.monitor(U, h=1e9, ucl=sc.t2_ucl(P, 0.001), lam=0.2)
    assert r.alarm[1] and not r.alarm[2]
    assert r.q[2] == 0.0             # 경보 직후 z가 0으로 돌아감


def test_refined_baseline_drops_outlier():
    outs = make_outings(12, n_lo=20, n_hi=30)
    outs[5] = outs[5] + 6.0          # 기준선 안의 이상 등판
    base, removed = sc.phase1_refined(outs, ucl=sc.t2_ucl(P, 0.01))
    assert 5 in removed


def test_n_min():
    assert sc.n_min(1.0, 0.5) == 4.0


def test_one_feature_and_nan_guard():
    rng = np.random.default_rng(1)
    outs = [rng.normal(0, 1, int(rng.integers(3, 12))) for _ in range(20)]   # p = 1, 1차원
    base = sc.phase1(outs)
    u = sc.outing_u(np.array([0.0]), 5, base)
    assert u.shape == (1,)
    U = np.array([0.1, 0.2, np.nan])
    try:
        sc.monitor(U, h=5.0, ucl=10.8, lam=0.2)
        assert False, "NaN이 있으면 오류가 나야 함"
    except ValueError:
        pass
