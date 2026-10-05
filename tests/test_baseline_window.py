"""기준선 구간 규칙 테스트 (SPEC 3.7). 실행: python -m pytest -q"""
import pandas as pd

from src.common import baseline_window as bw

RULES = {"starter_outings": 8, "reliever_outings": 15, "reliever_min_fastballs": 120}


def outings(pitcher, role, n_fb_list, season=2023, eligible_from=3):
    days = pd.date_range(f"{season}-04-01", periods=len(n_fb_list), freq="3D")
    return pd.DataFrame({"pitcher": pitcher, "season": season, "role": role, "game_pk": range(1000 * pitcher, 1000 * pitcher + len(n_fb_list)),
                         "game_date": days, "n_fb": n_fb_list, "eligible": [n >= eligible_from for n in n_fb_list]})


def window(df):
    return bw.baseline_windows(df, RULES).set_index("pitcher")


def test_starter_baseline_is_the_first_eight_eligible_outings():
    w = window(outings(1, "SP", [40] * 10)).loc[1]
    assert w["n_baseline"] == 8
    assert w["baseline_games"] == list(range(1000, 1008))
    assert w["baseline_end"] == pd.Timestamp("2023-04-22")


def test_ineligible_outings_are_skipped_not_counted():
    w = window(outings(1, "SP", [40, 1, 40, 40, 40, 40, 40, 40, 40, 40])).loc[1]
    assert w["baseline_games"] == [1000, 1002, 1003, 1004, 1005, 1006, 1007, 1008]


def test_starter_without_eight_eligible_outings_has_no_baseline():
    w = window(outings(1, "SP", [40] * 7)).loc[1]
    assert w["n_baseline"] == 0 and w["baseline_games"] == [] and pd.isna(w["baseline_end"])


def test_reliever_baseline_needs_fifteen_outings_and_120_fastballs_whichever_comes_later():
    w = window(pd.concat([outings(1, "RP", [10] * 20), outings(2, "RP", [5] * 30), outings(3, "RP", [5] * 16)]))
    assert w.loc[1, "n_baseline"] == 15          # 15등판에서 이미 150구
    assert w.loc[2, "n_baseline"] == 24          # 5구씩이면 24번째 등판에서 120구
    assert w.loc[3, "n_baseline"] == 0           # 16등판을 던졌지만 80구뿐


def test_each_season_gets_its_own_baseline():
    df = pd.concat([outings(1, "SP", [40] * 9, season=2022), outings(1, "SP", [40] * 3, season=2023)])
    w = bw.baseline_windows(df, RULES).set_index("season")
    assert w.loc[2022, "n_baseline"] == 8 and w.loc[2023, "n_baseline"] == 0


def test_phase_marks_baseline_then_monitoring_and_leaves_the_rest_blank():
    df = pd.concat([outings(1, "SP", [40] * 8 + [1, 40]), outings(2, "SP", [40] * 5)])
    phase = bw.phase(df, RULES)
    assert list(phase[df["pitcher"] == 1]) == ["baseline"] * 8 + ["", "monitor"]     # 부적격 등판은 감시하지 않음
    assert list(phase[df["pitcher"] == 2]) == [""] * 5                               # 기준선이 없으면 감시도 없음
