"""구장 보정 테스트 (SPEC 3.5). 실행: python -m pytest -q"""
import numpy as np
import pandas as pd

from src.common import park

RULES = {"features": ["rel_z"], "min_prior_outings": 30, "iterations": 20}
OFFSETS = {1: 0.10, 2: -0.05, 3: -0.05}          # 구장별 측정 차이 (평균 0)


def season(rng, year=2022, offsets=OFFSETS, pitchers=30, weeks=12, noise=0.02):
    """투수마다 주 2회, 무작위 구장에서 던진 한 시즌. rel_z = 투수 평균 + 구장 효과 + 잡음. 첫 주는 월요일에 시작한다."""
    monday = pd.Timestamp(f"{year}-04-04") - pd.Timedelta(days=pd.Timestamp(f"{year}-04-04").weekday())
    rows = []
    for p in range(pitchers):
        level = 6.0 + 0.3 * rng.standard_normal()
        for w in range(weeks):
            for day in rng.choice(7, size=2, replace=False):
                venue = int(rng.choice(list(offsets)))
                rows.append({"pitcher": p, "season": year, "game_pk": year * 100000 + len(rows), "week": w,
                             "game_date": monday + pd.Timedelta(days=7 * w + int(day)), "venue": venue, "eligible": True,
                             "rel_z": level + offsets[venue] + noise * rng.standard_normal()})
    return pd.DataFrame(rows)


def test_effects_recover_the_venue_offsets():
    got = park.effects(season(np.random.default_rng(0)), "rel_z", iterations=20)
    assert np.allclose(got.reindex([1, 2, 3]), [0.10, -0.05, -0.05], atol=0.01)
    assert abs(got.mean()) < 1e-9                                   # 구장 전체 평균은 0


def test_adjustments_use_only_what_was_known_before_that_week():
    d = season(np.random.default_rng(1))
    later = d.copy()
    later.loc[(later["week"] >= 6) & (later["venue"] == 1), "rel_z"] += 1.0      # 6주차부터 1번 구장 기록을 바꿔도
    before, after = park.adjustments(d, "rel_z", RULES), park.adjustments(later, "rel_z", RULES)
    early = d["week"] <= 6
    assert np.allclose(before[early], after[early])                 # 6주차까지의 보정값은 그대로 (6주차는 5주차까지만 봄)
    assert not np.allclose(before[d["week"] == 8], after[d["week"] == 8])


def test_a_venue_with_few_earlier_outings_falls_back_to_last_season_or_zero():
    rng = np.random.default_rng(2)
    first, second = season(rng, 2021), season(rng, 2022, offsets={1: 0.10, 2: -0.05, 3: -0.05, 9: 0.30})
    used = park.adjustments(pd.concat([first, second], ignore_index=True), "rel_z", RULES)
    first_used, second_used = used.iloc[:len(first)], used.iloc[len(first):]
    assert (first_used[first["week"].to_numpy() == 0] == 0).all()   # 첫 시즌 첫 주: 아는 것이 없어 보정하지 않음
    opening = second[second["week"] == 0]
    known = opening["venue"] != 9
    assert np.allclose(second_used[opening.index[known] + len(first)], opening.loc[known, "venue"].map(OFFSETS), atol=0.01)
    assert (second_used[opening.index[~known] + len(first)] == 0).all()        # 작년에 없던 구장은 0


def test_this_seasons_estimate_takes_over_once_enough_outings_exist():
    rng = np.random.default_rng(3)
    first, second = season(rng, 2021), season(rng, 2022, offsets={1: -0.10, 2: 0.05, 3: 0.05})    # 올해는 반대로 어긋남
    used = park.adjustments(pd.concat([first, second], ignore_index=True), "rel_z", RULES).iloc[len(first):]
    at_one = (second["venue"] == 1).to_numpy()
    week = second["week"].to_numpy()
    assert np.allclose(used[at_one & (week == 0)], 0.10, atol=0.01)            # 처음에는 작년 값
    assert np.allclose(used[at_one & (week == 11)], -0.10, atol=0.01)          # 기록이 쌓이면 올해 값


def test_adjust_shifts_outing_means_and_their_pitches_by_the_same_amount():
    rng = np.random.default_rng(4)
    outings = season(rng).assign(velo=94.0)
    outings.loc[5, ["eligible", "rel_z"]] = [False, np.nan]         # 주력 패스트볼이 없던 등판
    outings.loc[6, "venue"] = np.nan                                # 구장을 모르는 등판
    pitches = pd.DataFrame({"pitcher": outings["pitcher"].repeat(2).to_numpy(), "season": 2022,
                            "game_pk": outings["game_pk"].repeat(2).to_numpy(),
                            "rel_z": outings["rel_z"].repeat(2).to_numpy(), "velo": 94.0})
    adjusted, moved = park.adjust(outings, pitches, RULES)
    assert np.allclose((adjusted["rel_z"] + adjusted["park_rel_z"]).dropna(), outings["rel_z"].dropna())
    assert adjusted["park_rel_z"].abs().max() > 0.05 and adjusted.loc[6, "park_rel_z"] == 0
    late = adjusted.index[adjusted["week"] == 11][0]
    shift = pitches.loc[2 * late, "rel_z"] - moved.loc[2 * late, "rel_z"]
    assert np.isclose(shift, adjusted.loc[late, "park_rel_z"]) and np.isclose(moved.loc[2 * late + 1, "rel_z"], moved.loc[2 * late, "rel_z"])
    assert (adjusted["velo"] == 94.0).all() and (moved["velo"] == 94.0).all()   # 다른 특징은 건드리지 않음


def test_last_seasons_value_is_ignored_for_a_venue_that_had_too_few_outings_then():
    rng = np.random.default_rng(5)
    first, second = season(rng, 2021), season(rng, 2022)
    first.loc[first.index[:5], ["venue", "rel_z"]] = [7, 6.5]       # 작년에 다섯 등판만 열린 특별 구장
    second.loc[second.index[0], "venue"] = 7                        # 올해 첫 주에 다시 열림
    used = park.adjustments(pd.concat([first, second], ignore_index=True), "rel_z", RULES)
    assert used.iloc[len(first)] == 0
