"""합동 Σ_b와 기준선 조립 테스트 (SPEC 3.7~3.8). 실행: python -m pytest -q"""
import numpy as np
import pytest

from src.common import monitoring as mon
from src.core import stats_core as sc

P = 3
SB = np.diag([0.25, 0.30, 0.20])        # 등판 간 공분산 (등판 안 분산 = 1인 단위)
UCL = sc.t2_ucl(P, 0.01)


def outings(rng, m, mean_n=40, sb=SB):
    out = []
    for _ in range(m):
        n = max(3, int(rng.poisson(mean_n)))
        out.append(rng.multivariate_normal(np.zeros(P), sb) + rng.standard_normal((n, P)))
    return out


def test_pooled_sigma_b_recovers_the_between_outing_covariance():
    rng = np.random.default_rng(0)
    pooled = mon.pooled_sigma_b([outings(rng, 8) for _ in range(600)], floor=0.01)
    assert np.allclose(pooled, SB, atol=0.03)


def test_pooled_sigma_b_lifts_small_eigenvalues_to_the_floor():
    rng = np.random.default_rng(1)
    flat = np.diag([0.25, 0.30, 0.0])                # 세 번째 특징은 등판 간 변동이 없음
    pooled = mon.pooled_sigma_b([outings(rng, 8, sb=flat) for _ in range(200)], floor=0.01)
    assert np.linalg.eigvalsh(pooled).min() >= 0.01 - 1e-12


def test_assembled_baseline_keeps_u_variance_at_one_with_only_eight_outings():
    rng = np.random.default_rng(2)
    u = []
    for _ in range(1500):
        base = mon.assemble(outings(rng, 8), SB)
        u += [sc.outing_u(o.mean(0), len(o), base) for o in outings(rng, 4)]
    assert np.allclose(np.var(u, axis=0), 1.0, atol=0.08)      # 평균 추정 오차 보정이 없으면 1.13쯤 나옴


def test_assemble_uses_the_pitchers_own_mean_and_within_covariance():
    rng = np.random.default_rng(3)
    base_outings = outings(rng, 8)
    own = sc.phase1(base_outings)
    base = mon.assemble(base_outings, SB)
    assert np.allclose(base.mu, own.mu) and np.allclose(base.Sw, own.Sw)
    assert base.n_outings == 8


def test_refine_flags_a_gross_outlier_outing():
    rng = np.random.default_rng(4)
    base_outings = outings(rng, 8)
    base_outings[5] = base_outings[5] + 4.0
    assert mon.refine(base_outings, SB, UCL) == [5]


def test_refine_rarely_flags_ordinary_outings():
    rng = np.random.default_rng(5)
    flagged = sum(len(mon.refine(outings(rng, 8), SB, UCL)) for _ in range(300))
    assert flagged / (300 * 8) < 0.04                 # 투수별 Σ_b로 정제하면 약 20%가 빠진다


def test_refine_never_leaves_fewer_than_three_outings():
    rng = np.random.default_rng(6)
    base_outings = outings(rng, 4)
    base_outings[0] = base_outings[0] + 9.0
    base_outings[1] = base_outings[1] - 9.0
    assert mon.refine(base_outings, SB, UCL) == []


def test_fit_baseline_does_not_depend_on_feature_units():
    rng = np.random.default_rng(7)
    base_outings, new = outings(rng, 8), outings(rng, 1)[0]
    units = np.array([10.0, 0.5, 3.0])
    scale, base, _ = mon.fit_baseline(base_outings, SB, UCL)
    scale2, base2, _ = mon.fit_baseline([o * units for o in base_outings], SB, UCL)
    assert np.allclose(mon.standardize([new], scale, base), mon.standardize([new * units], scale2, base2))


def test_marginal_baseline_matches_a_baseline_built_from_that_feature_alone():
    rng = np.random.default_rng(8)
    base_outings = outings(rng, 8)
    velo_only = mon.assemble([o[:, :1] for o in base_outings], SB[:1, :1])
    marginal = mon.marginal(mon.assemble(base_outings, SB), [0])
    assert np.allclose(marginal.mu, velo_only.mu)
    assert np.allclose(marginal.Sb, velo_only.Sb) and np.allclose(marginal.Sw, velo_only.Sw)


def test_outing_arrays_groups_pitches_by_outing_in_feature_order():
    import pandas as pd
    fb = pd.DataFrame({"pitcher": [1, 1, 1, 2], "season": 2022, "game_pk": [10, 10, 11, 10],
                       "velo": [94.0, 95.0, 93.0, 90.0], "rel_z": [6.0, 6.1, 5.9, 5.5], "spin": [1, 2, 3, 4]})
    arrays = mon.outing_arrays(fb, ["rel_z", "velo"])
    assert set(arrays) == {(1, 2022, 10), (1, 2022, 11), (2, 2022, 10)}
    assert arrays[(1, 2022, 10)].tolist() == [[6.0, 94.0], [6.1, 95.0]]


def _pitcher_season(rng, n_outings=11):
    """투수 1의 2022 시즌: 등판 n_outings개(각 20구 안팎). 등판 표·투구 표·배열을 함께 돌려준다."""
    import pandas as pd
    fb_rows, outing_rows = [], []
    for game in range(n_outings):
        x = np.array([94.0, 6.0, 40.0]) + rng.multivariate_normal(np.zeros(P), SB) + rng.standard_normal((20, P))
        fb_rows += [{"pitcher": 1, "season": 2022, "game_pk": game, "velo": a, "rel_z": b, "arm_angle": c} for a, b, c in x]
        outing_rows.append({"pitcher": 1, "season": 2022, "role": "SP", "game_pk": game,
                            "game_date": pd.Timestamp("2022-04-01") + pd.Timedelta(days=5 * game), "n_fb": 20, "eligible": True})
    return pd.DataFrame(outing_rows), pd.DataFrame(fb_rows)


def test_baseline_row_round_trips_through_the_saved_table():
    rng = np.random.default_rng(9)
    scale, base, _ = mon.fit_baseline(outings(rng, 8), SB, UCL)
    row = {"scale": scale.tolist(), "fixed_mu": base.mu.tolist(), "fixed_Sw": base.Sw.ravel().tolist(),
           "fixed_Sb": base.Sb.ravel().tolist(), "n_baseline": 8, "fixed_removed": 0}
    again = mon.to_baseline(row)
    assert np.allclose(again.mu, base.mu) and np.allclose(again.Sb, base.Sb) and np.allclose(again.Sw, base.Sw)


def test_fixed_table_covers_only_outings_after_the_baseline_in_date_order():
    import pandas as pd
    rng = np.random.default_rng(10)
    outing_table, fb = _pitcher_season(rng)
    features = ["velo", "rel_z", "arm_angle"]
    arrays = mon.outing_arrays(fb, features)
    rules = {"starter_outings": 8, "reliever_outings": 15, "reliever_min_fastballs": 120}
    scale, base, _ = mon.fit_baseline([arrays[(1, 2022, g)] for g in range(8)], SB, UCL)
    fits = pd.DataFrame([{"pitcher": 1, "season": 2022, "role": "SP", "scale": scale.tolist(),
                          "fixed_mu": base.mu.tolist(), "fixed_Sw": base.Sw.ravel().tolist(),
                          "fixed_Sb": base.Sb.ravel().tolist(), "n_baseline": 8, "fixed_removed": 0}])
    table = mon.fixed_table(outing_table.sample(frac=1, random_state=0), arrays, fits, rules, features)
    assert list(table["game_pk"]) == [8, 9, 10]
    expected = mon.standardize([arrays[(1, 2022, 9)]], scale, base)[0]
    got = table.loc[table["game_pk"] == 9, ["u_velo", "u_rel_z", "u_arm_angle"]].to_numpy()[0]
    assert np.allclose(got, expected)
    assert table.loc[table["game_pk"] == 9, "t2"].iloc[0] == pytest.approx(float(expected @ expected))


def test_run_charts_restarts_for_every_pitcher_season():
    import pandas as pd
    rng = np.random.default_rng(11)
    u = rng.standard_normal((12, P)) * 1.5
    table = pd.DataFrame(u, columns=["u_velo", "u_rel_z", "u_arm_angle"]).assign(
        pitcher=[1] * 6 + [2] * 6, season=2022, t2=(u ** 2).sum(axis=1))
    out = mon.run_charts(table, ["velo", "rel_z", "arm_angle"], {0.2: (4.0, 9.0)}, reset_after_alarm=True)
    for pitcher, rows in ((1, slice(0, 6)), (2, slice(6, 12))):
        direct = sc.monitor(u[rows], h=4.0, ucl=9.0, lam=0.2)
        mine = out[out["pitcher"] == pitcher]
        assert np.allclose(mine["q_0.2"], direct.q)              # 다른 투수의 값이 넘어오지 않음
        assert list(mine["alarm_0.2"]) == list(direct.alarm)
    assert out["alarm_0.2"].any()                                 # 이 한계에서는 경보가 실제로 울리는 자료


def test_calibration_by_n_reports_u_variance_per_pitch_count_bin():
    import pandas as pd
    table = pd.DataFrame({"role": "RP", "n_fb": [3, 5, 6, 9, 10, 15, 16, 40],
                          "u_velo": [1.0, -1.0, 2.0, -2.0, 0.5, -0.5, 3.0, -3.0], "t2": [1.0, 1.0, 4.0, 4.0, 0.25, 0.25, 9.0, 9.0]})
    got = mon.calibration_by_n(table, ["velo"], [3, 6, 10, 16]).set_index("n_fb_bin")
    assert list(got.index) == ["3~5", "6~9", "10~15", "16+"]
    assert list(got["outings"]) == [2, 2, 2, 2]
    assert got.loc["6~9", "var_u_velo"] == pytest.approx(8.0)       # 표본분산 (2, −2)
    assert got.loc["16+", "mean_t2"] == pytest.approx(9.0)


# ---- 움직이는 기준선 (수준이 천천히 움직이는 모형) ----
Q_TRUE = np.array([[0.04, 0.01, 0.0], [0.01, 0.06, 0.02], [0.0, 0.02, 0.05]])     # 수준이 한 등판 사이에 움직이는 공분산
SE_TRUE = np.diag([0.30, 0.60, 0.25])                                             # 등판마다 흔들리는 공분산
TRUE = mon.Dynamics(Q=Q_TRUE, Se=SE_TRUE)


def wandering_season(rng, t=30, mean_n=10, jump=None):
    """수준이 조금씩 움직이는 한 시즌: (등판 평균 t×P, 투구 수 t, Σ_w). 등판 안 분산은 1."""
    level, means, counts = rng.standard_normal(P), [], []
    for i in range(t):
        if i:
            level = level + rng.multivariate_normal(np.zeros(P), Q_TRUE)
        if jump and i == jump[0]:
            level = level + jump[1]
        n = max(3, int(rng.poisson(mean_n)))
        means.append(level + rng.multivariate_normal(np.zeros(P), SE_TRUE) + rng.standard_normal((n, P)).mean(0))
        counts.append(n)
    return np.array(means), np.array(counts, dtype=float), np.eye(P)


def test_pooled_dynamics_recovers_level_step_and_outing_noise():
    rng = np.random.default_rng(20)        # Q는 큰 값들의 차로 구해져 표본이 많아야 한다 (600시즌이면 오차 0.03쯤)
    got = mon.pooled_dynamics([wandering_season(rng) for _ in range(3000)], q_floor=0.001, e_floor=0.01)
    assert np.allclose(got.Q, Q_TRUE, atol=0.02)
    assert np.allclose(got.Se, SE_TRUE, atol=0.03)


def test_follow_gives_unit_variance_uncorrelated_u_all_season_long():
    rng = np.random.default_rng(21)
    early, late, pairs = [], [], []
    for _ in range(500):
        means, n, sw = wandering_season(rng)
        u = mon.follow(means, n, sw, TRUE, n_start=8, skip_ucl=UCL).u
        early.append(u[:5])
        late.append(u[-5:])
        pairs.append(np.column_stack([u[1:, 0], u[:-1, 0]]))
    assert np.allclose(np.var(np.concatenate(early), axis=0), 1.0, atol=0.1)
    assert np.allclose(np.var(np.concatenate(late), axis=0), 1.0, atol=0.1)      # 시즌 끝에서도 그대로
    lag = np.concatenate(pairs)
    assert abs(np.corrcoef(lag[:, 0], lag[:, 1])[0, 1]) < 0.05                   # 앞 등판과 무관


def test_follow_keeps_u_variance_at_one_for_short_and_long_outings():
    rng = np.random.default_rng(22)
    short, long_ = [], []
    for _ in range(400):
        means, n, sw = wandering_season(rng, mean_n=4)
        short.append(mon.follow(means, n, sw, TRUE, 8, UCL).u)
        means, n, sw = wandering_season(rng, mean_n=45)
        long_.append(mon.follow(means, n, sw, TRUE, 8, UCL).u)
    assert np.allclose(np.var(np.concatenate(short), axis=0), 1.0, atol=0.08)
    assert np.allclose(np.var(np.concatenate(long_), axis=0), 1.0, atol=0.08)


def test_follow_monitors_only_outings_after_the_start_up_period():
    means, n, sw = wandering_season(np.random.default_rng(23), t=12)
    result = mon.follow(means, n, sw, TRUE, n_start=8, skip_ucl=UCL)
    assert result.u.shape == (4, P) and result.expected.shape == (4, P) and result.cov.shape == (4, P, P)


def test_follow_flags_a_sudden_change_then_adapts_to_the_new_level():
    rng = np.random.default_rng(24)
    first, later = [], []
    for _ in range(300):
        means, n, sw = wandering_season(rng, t=30, mean_n=30, jump=(15, np.array([-2.0, 0.0, 0.0])))
        u = mon.follow(means, n, sw, TRUE, 8, UCL).u
        first.append(u[15 - 8, 0])          # 변화가 일어난 등판
        later.append(u[-1, 0])              # 14등판 뒤
    assert np.mean(first) < -2.0            # 예상보다 크게 낮음
    assert abs(np.mean(later)) < 0.2        # 새 수준을 따라간 뒤에는 평소대로


def test_follow_ignores_a_wild_outing_during_start_up():
    rng = np.random.default_rng(25)
    means, n, sw = wandering_season(rng, t=12, mean_n=30)
    spoiled = means.copy()
    spoiled[7] += 8.0                        # 시작 구간의 마지막 등판이 크게 튐
    clean = mon.follow(means, n, sw, TRUE, 8, UCL)
    again = mon.follow(spoiled, n, sw, TRUE, 8, UCL)
    assert np.allclose(again.expected[0], mon.follow(means[[0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11]], n[[0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11]], sw, TRUE, 7, UCL).expected[0])
    assert np.abs(again.u[0] - clean.u[0]).max() < 1.0        # 튄 등판이 평소를 끌고 가지 않음


def test_follow_works_for_a_single_feature():
    means, n, sw = wandering_season(np.random.default_rng(26), t=12)
    one = mon.Dynamics(Q=Q_TRUE[:1, :1], Se=SE_TRUE[:1, :1])
    assert mon.follow(means[:, :1], n, sw[:1, :1], one, 8, sc.t2_ucl(1, 0.01)).u.shape == (4, 1)
