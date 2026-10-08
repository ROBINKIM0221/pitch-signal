"""기록지 맨 아래 '투구수' 줄 판독(숫자 조각 나누기·누적 사슬 풀기·이닝별 투수 몫) 테스트. 실행: python -m pytest -q tests/test_scoresheet_row.py"""
import numpy as np
import pandas as pd

from src.common import scoresheet_row as sr


def one_hot(digits, p=0.9):
    """숫자열 → 숫자마다 그 숫자에 p, 나머지에 고르게 나눈 확률 (m×10)."""
    P = np.full((len(digits), 10), (1 - p) / 9)
    for i, d in enumerate(digits):
        P[i, int(d)] = p
    return P


def table(value, p=0.9):
    """'value'라고 읽힌 수 하나의 값 표."""
    return sr.number_table([(0.0, one_hot(str(value), p))])


def test_seg_prior_never_penalizes_a_narrow_single_digit():
    assert sr.seg_prior(0.4, 1) == 0.0                           # 좁은 '1' 하나
    assert sr.seg_prior(1.0, 1) == 0.0


def test_seg_prior_penalizes_cutting_one_digit_into_narrow_pieces():
    assert sr.seg_prior(1.0, 2) < sr.seg_prior(1.0, 1) - 1.0
    assert sr.seg_prior(1.0, 3) < sr.seg_prior(1.0, 2)


def test_seg_prior_prefers_two_pieces_for_a_double_width_blob():
    assert sr.seg_prior(2.2, 2) > sr.seg_prior(2.2, 1)
    assert sr.seg_prior(2.2, 2) > sr.seg_prior(2.2, 3)


def test_cut_splits_at_the_faintest_column():
    m = np.zeros((10, 13), np.uint8); m[:, 0:5] = 1; m[:, 8:13] = 1; m[4, 5:8] = 1   # 두 숫자가 가는 획 하나로 이어짐
    pieces = sr.cut(dict(mask=m, w=13), 2)
    assert len(pieces) == 2 and pieces[0].shape[1] == 5            # 왼쪽 숫자는 이음 획 앞에서 깨끗이 떨어진다
    assert sum(int(p.sum()) for p in pieces) == int(m.sum())     # 잉크를 잃지 않는다


def test_hypotheses_keep_at_most_three_digits():
    comps = [dict(mask=np.ones((10, 30), np.uint8), w=30, h=10), dict(mask=np.ones((10, 8), np.uint8), w=8, h=10)]
    hs = sr.hypotheses(comps, w_digit=8.0)
    assert hs and all(1 <= len(pcs) <= 3 for _, pcs in hs)
    assert any(len(pcs) == 3 for _, pcs in hs)                   # 넓은 덩어리를 둘로 + 낱자 하나


def test_value_table_forbids_leading_zero_for_multi_digit_numbers():
    t = table("07")
    assert t[7] < t[17]                                          # '07'은 7로 읽지 않는다 (두 자리면 10 이상)


def test_number_table_missing_number_is_flat_and_read_number_has_floor():
    miss = sr.number_table([])
    assert np.allclose(miss, miss[0])
    t = table(43)
    assert t.argmax() == 43 and t[143] == sr.FLOOR_LP           # 자릿수가 달라도 바닥 확률로 지나갈 수 있다


def test_chain_decode_recovers_innings_from_consistent_row():
    inns = [10, 15, 8, 9]
    cums = np.cumsum(inns)
    tabs = [(None, table(cums[0]), False)] + [(table(v), table(c), False) for v, c in zip(inns[1:], cums[1:])]
    assert sr.chain_decode(tabs, total=int(cums[-1])) == inns


def test_chain_decode_fixes_a_misread_cumulative_with_the_chain():
    tabs = [(None, table(10), False), (table(15), table(26), False), (table(8), table(33), False)]   # 25를 26으로 잘못 읽음
    assert sr.chain_decode(tabs, total=33) == [10, 15, 8]


def test_chain_decode_fills_a_missing_number_from_neighbours():
    tabs = [(None, table(12), False), (sr.number_table([]), table(23), False), (table(16), table(39), False)]
    assert sr.chain_decode(tabs, total=39) == [12, 11, 16]


def test_chain_decode_allows_zero_for_an_empty_bat_around_column():
    tabs = [(None, table(27), False), (table(23), table(50), False), (sr.number_table([]), np.zeros(sr.MAXV + 1), True),
            (table(45), table(95), False)]
    assert sr.chain_decode(tabs, total=95) == [27, 23, 0, 45]


def test_chain_decode_respects_anchor_cumulatives():
    tabs = [(None, table(10, 0.5), False), (table(15, 0.5), table(25, 0.5), False), (table(8, 0.5), table(33, 0.5), False)]
    out = sr.chain_decode(tabs, total=33, anchors={1: 11})        # 공식 기록으로 1회 끝 누적이 11이라면
    assert np.cumsum(out)[0] == 11 and sum(out) == 33


def test_chain_decode_keeps_at_least_one_pitch_per_plate_appearance():
    tabs = [(None, table(27), False), (table(23), table(50), False), (sr.number_table([]), np.zeros(sr.MAXV + 1), True),
            (table(45), table(95), False)]
    out = sr.chain_decode(tabs, total=95, lower={3: 4})             # 3열에 타석 4개 → 0구일 수 없다
    assert out[2] >= 4 and sum(out) == 95


def test_chain_decode_returns_none_when_total_unreachable():
    tabs = [(None, table(10), False)]
    assert sr.chain_decode(tabs, total=500) is None


def test_mark_prior_peaks_near_the_mark_count():
    pri = sr.mark_prior(14, lam=2.0)
    assert abs(int(np.argmax(pri)) - 14) <= 1
    assert np.allclose(sr.mark_prior(None, lam=2.0), 0.0)


def test_outing_innings_gives_whole_innings_the_row_total_and_remainder_to_shared_inning():
    T = {1: 14, 2: 20, 3: 18}
    pitchers = {1: {11}, 2: {11}, 3: {11, 21}}                    # 3회 도중 교체
    marks = pd.DataFrame({"inning": [1] * 14 + [2] * 19 + [3] * 8 + [3] * 9, "number": [11] * 41 + [21] * 9,
                          "ball": [1] * 5 + [0] * 9 + [1] * 8 + [0] * 11 + [1] * 2 + [0] * 6 + [0] * 9})
    out = sr.outing_innings(11, official=40, T=T, pitchers=pitchers, marks=marks, tol=(2, 0.15))
    assert [r["inning"] for r in out] == [1, 2, 3]
    assert [r["pitches"] for r in out] == [14, 20, 6]           # 3회 몫 = 공식 40 − (14 + 20)
    assert [r["shared"] for r in out] == [False, False, True]
    assert out[0]["balls"] == 5 and out[0]["strikes"] == 9      # 표시 14개 중 볼 5 → 투구 14에 그대로
    assert out[1]["balls"] == round(20 * 8 / 19) and out[1]["balls"] + out[1]["strikes"] == 20


def test_outing_innings_hides_ball_strike_when_inning_marks_disagree_with_row():
    T = {1: 20}
    marks = pd.DataFrame({"inning": [1] * 12, "number": [11] * 12, "ball": [1] * 4 + [0] * 8})
    out = sr.outing_innings(11, official=20, T=T, pitchers={1: {11}}, marks=marks, tol=(2, 0.15))
    assert out[0]["pitches"] == 20 and out[0]["balls"] is None and out[0]["strikes"] is None


def test_outing_innings_is_empty_when_an_inning_gets_no_pitch():
    T = {1: 0, 2: 20}
    marks = pd.DataFrame({"inning": [1] * 5 + [2] * 20, "number": [11] * 25, "ball": [0] * 25})
    assert sr.outing_innings(11, official=20, T=T, pitchers={1: {11}, 2: {11}}, marks=marks, tol=(2, 0.15)) == []


def test_outing_innings_is_empty_when_row_contradicts_official_total():
    T = {1: 14, 2: 20}
    marks = pd.DataFrame({"inning": [1] * 14 + [2] * 20, "number": [11] * 34, "ball": [0] * 34})
    assert sr.outing_innings(11, official=30, T=T, pitchers={1: {11}, 2: {11}}, marks=marks, tol=(2, 0.15)) == []
