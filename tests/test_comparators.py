"""비교 대상 B1~B4 테스트 (SPEC 3.12). 실행: python -m pytest -q"""
import numpy as np
import pandas as pd
import pytest

from src.common import comparators as cp
from src.core import stats_core as sc

B2 = {"cusum_k": 0.5, "ip_floor_outs": 1, "winsor_pct": 99}
B3 = {"window": 4, "shrink_to_baseline_diag": 0.5}


def test_whip_floors_outs_and_caps_extreme_values():
    outings = pd.DataFrame({"h": [3, 0, 8], "bb": [1, 0, 4], "outs": [9, 0, 1]})
    assert list(cp.whip(outings, floor_outs=1, cap=20.0)) == [4 / 3, 0.0, 20.0]      # 아웃 0개는 1개로, 36은 20으로 잘림


def test_b2_cusum_accumulates_only_upward_excess_and_restarts_after_an_alarm():
    w = np.array([0.0, 1.5, 1.5, 1.5, -5.0, 1.5, 1.5, 1.5])                            # 표준화한 WHIP
    alarm, s = cp.b2_cusum(w, k=0.5, h=2.5)
    assert list(np.round(s, 2)) == [0.0, 1.0, 2.0, 3.0, 0.0, 1.0, 2.0, 3.0]
    assert list(np.flatnonzero(alarm)) == [3, 7]                                       # 넘으면 울리고 0에서 다시


def test_b3_distance_compares_an_outing_with_its_previous_four():
    x = np.array([[94.0, 6.0, 40.0]] * 4 + [[92.0, 6.0, 40.0]])                        # 네 등판 그대로, 다섯째만 구속 −2
    sd = np.full((5, 3), [0.5, 0.1, 1.0])
    d2 = cp.b3_distance(x, sd, window=4, shrink=0.5)
    assert np.isnan(d2[:4]).all()                                                      # 앞 네 등판은 비교 대상이 모자람
    assert d2[4] == pytest.approx(4.0 / (0.5 * 0.25))                                  # 표본 공분산 0이라 대각 수축분만 남음: 2²/(0.5·0.5²)


def test_b4_is_the_two_sided_velocity_ewma_from_the_core():
    uv = 1.5 * np.random.default_rng(0).standard_normal(200)
    alarm, q = cp.b4_ewma(uv, h=5.74, lam=0.2)
    chart = sc.monitor(uv, 5.74, np.inf, 0.2)
    assert (alarm == chart.alarm).all() and np.allclose(q, chart.q) and alarm.sum() > 2


def test_threshold_for_rate_finds_the_lowest_limit_meeting_the_target():
    rng = np.random.default_rng(1)
    seasons = [rng.standard_normal(40) for _ in range(150)]
    h = cp.threshold_for_rate(lambda h: [cp.b2_cusum(w, 0.5, h)[0] for w in seasons], target=1.0)
    rate = 100 * np.concatenate([cp.b2_cusum(w, 0.5, h)[0] for w in seasons]).mean()
    assert 0.9 <= rate <= 1.0


def season_frame(pitcher, velo, h=None, bb=None, outs=None):
    n = len(velo)
    return pd.DataFrame({"pitcher": pitcher, "season": 2023, "role": "SP", "game_pk": range(n),
                         "game_date": pd.date_range("2023-04-01", periods=n, freq="5D"), "eligible": True,
                         "phase": ["baseline"] * 4 + ["monitor"] * (n - 4), "velo": velo, "rel_z": 6.0, "arm_angle": 40.0,
                         "h": h if h is not None else [4] * n, "bb": bb if bb is not None else [2] * n,
                         "outs": outs if outs is not None else [18] * n})


def test_statistics_table_lines_up_every_comparator_with_the_monitored_outings():
    outings = pd.concat([season_frame(1, [94, 94, 94, 94, 93.5, 92.5, 94.0], h=[4, 6, 2, 5, 9, 4, 4]),   # 2번 투수는 WHIP가 늘 같음
                         season_frame(2, [90] * 7)], ignore_index=True)
    monitored = outings[outings["phase"] == "monitor"][["pitcher", "season", "game_pk"]].assign(
        uv=[-1.0, -3.0, 0.0, 0.0, 0.0, 0.0], sd_velo=0.5, sd_rel_z=0.1, sd_arm_angle=1.0)
    stats = cp.statistics(outings, monitored, ["velo", "rel_z", "arm_angle"], {"B1": {"velo_drop_mph": 1.0}, "B2": B2, "B3": B3},
                          whip_cap=20.0)
    assert list(stats.columns[:3]) == ["pitcher", "season", "game_pk"] and len(stats) == 6
    one = stats[stats["pitcher"] == 1]
    assert list(one["b1_drop"]) == [0.5, 1.5, 0.0]                                     # 시작 구간 평균 94 − 등판 구속
    assert one["b2_w"].iloc[0] > one["b2_w"].iloc[1]                                   # 피안타 9개 등판의 WHIP가 더 높음
    assert one["b3_d2"].iloc[1] > one["b3_d2"].iloc[2] and np.isfinite(one["b3_d2"]).all()
    assert list(one["uv"]) == [-1.0, -3.0, 0.0]
