"""기록지 사진 판독(격자 찾기·표시 떼기·칸↔타석·검산·'평소보다 볼이 많았던 등판') 테스트. 실행: python -m pytest -q tests/test_scoresheet.py"""
import numpy as np
import pandas as pd

from src.common import scoresheet as ss


def pa(inning, slot, result="좌플"):
    return {"inning": inning, "slot": slot, "result": result, "events": []}


def test_cells_for_moves_to_next_column_when_lineup_bats_around():
    pas = [pa(1, s) for s in range(1, 10)] + [pa(1, 1), pa(1, 2)] + [pa(2, 3), pa(2, 4), pa(2, 5)]
    cells = ss.cells_for(pas)
    assert cells[:9] == [(1, s) for s in range(1, 10)]
    assert cells[9:11] == [(2, 1), (2, 2)]                     # 같은 이닝에 1번 타자가 다시 → 다음 열
    assert cells[11:] == [(3, 3), (3, 4), (3, 5)]               # 다음 이닝은 그다음 열부터


def test_cells_for_gives_no_cell_to_tiebreak_runner():
    cells = ss.cells_for([pa(10, 4, "승부주자"), pa(10, 5)])
    assert cells == [None, (1, 5)]


def test_snap_moves_to_nearest_strong_line_within_tolerance():
    prof = np.zeros(200); prof[103] = 50; prof[150] = 5
    out, hit = ss.snap(prof, np.array([100.0, 150.0, 180.0]), tol=4, min_val=30)
    assert abs(out[0] - 103) <= 1 and hit[0]                     # 3px 합으로 고르므로 1px 안
    assert out[1] == 150 and not hit[1]                         # 약한 선이면 예측 그대로
    assert out[2] == 180 and not hit[2]


def synthetic_grid(a=0.97, b=12.0, top=210, row_h=None, H=1100, W=1600):
    """양식 패턴을 a배·b px 옮겨 그린 인쇄선 마스크: 이닝 칸 경계·띠 경계(1~9줄에만)·가로선(머리 줄·1~10줄·아래 합계 줄)."""
    row_h = row_h or ss.ROW_H * a
    v = np.zeros((H, W), np.uint8); h = np.zeros((H, W), np.uint8)
    bot = int(round(top + 9 * row_h))
    for x in a * ss.TL + b:                                     # 칸 경계: 머리 줄부터 10번째 줄까지
        v[int(top - row_h):int(top + 10 * row_h), int(round(x))] = 255
    for x in a * ss.TS + b:                                     # 띠 경계: 타순 1~9줄에만
        v[top:bot, int(round(x))] = 255
    for x in a * np.array([46, 68, 89, 111, 133, 154, 176]) + b:   # 왼쪽 정보 칸 선 (이름 칸 184~291에는 없음)
        v[int(top - row_h):int(top + 10 * row_h), int(round(x))] = 255
    for y in [top - row_h + k * row_h for k in range(12)]:      # 머리 줄 위 ~ 10번째 줄 아래
        h[int(round(y)), int(round(a * 40 + b)):int(round(a * 1580 + b))] = 255
    return h, v, bot


def test_comb_finds_inning_columns_and_scale():
    h, v, _ = synthetic_grid(a=0.97, b=12.0)
    a, b, score, margin = ss.comb_x(v)
    assert np.abs((a * ss.TX + b) - (0.97 * ss.TX + 12.0)).max() <= 2.5   # 빗은 ±2px를 허용한다 (정확한 자리는 국소 붙이기가 잡음)
    assert margin > 0                                           # 한 칸 밀린 맞춤보다 점수가 높다


def test_row_window_finds_the_nine_strip_rows():
    h, v, bot = synthetic_grid(a=1.0, b=0.0, top=230)
    X = 1.0 * ss.TX
    top, bottom, _ = ss.row_window(v, h, X, 1.0)
    assert abs(top - 230) <= 2 and abs(bottom - bot) <= 2


def blob(img, y, x, r=3):
    yy, xx = np.ogrid[:img.shape[0], :img.shape[1]]
    img[(yy - y) ** 2 + (xx - x) ** 2 <= r * r] = 255


def test_cell_marks_splits_marks_joined_by_a_thin_bridge():
    ink = np.zeros((60, 16), np.uint8)
    blob(ink, 10, 7); blob(ink, 22, 7)
    ink[13:20, 7] = 255                                         # 1px 다리로 이어진 두 표시
    marks = ss.cell_marks(ink, (0, 0, 16, 60))
    assert len(marks) == 2


def test_cell_marks_keeps_stacked_strokes_apart_and_rejoins_side_by_side_pieces():
    ink = np.zeros((60, 16), np.uint8)
    for i in range(5):                                          # 위아래로 겹치게 쌓인 대각선 획 두 개 (서로 닿지 않음)
        ink[5 + i, 3 + i] = 255; ink[8 + i, 9 + i // 2] = 255
    ink[30:36, 2:4] = 255; ink[30:36, 8:10] = 255               # 옆으로 나란한 두 조각 (끊긴 동그라미)
    marks = ss.cell_marks(ink, (0, 0, 16, 60))
    assert len(marks) == 3


def test_drop_small_fragments_relative_to_sheet():
    areas = pd.Series([40, 42, 38, 9, 45, 10, 41])
    keep = ss.keep_relative(areas, frac=0.25)
    assert keep.tolist() == [True, True, True, False, True, True, True]   # 기준 = 중앙값 40의 25% = 10


def test_outing_gate_and_ball_rate():
    marks = pd.DataFrame({"game_idx": [1] * 10 + [2] * 6, "team": ["가"] * 16, "number": [17] * 16,
                          "ball": [1, 0, 0, 1, 0, 0, 0, 1, 0, 0] + [1, 1, 0, 0, 0, 0]})
    official = pd.DataFrame({"game_idx": [1, 2], "team": ["가", "가"], "number": [17, 17], "pitches": [11, 10]})
    o = ss.outing_table(marks, official, tol=0.15).set_index("game_idx")
    assert o.loc[1, "marks"] == 10 and o.loc[1, "gate"] and abs(o.loc[1, "ball_pct"] - 0.3) < 1e-9   # 10/11 = 9% 차이 → 통과
    assert not o.loc[2, "gate"] and np.isnan(o.loc[2, "ball_pct"])                                      # 6/10 = 40% 차이 → 보여 주지 않음


def test_usual_flag_needs_enough_pitches_and_history():
    o = pd.DataFrame({"team": ["가"] * 5, "number": [17] * 5, "game_idx": range(1, 6),
                      "pitches": [60, 60, 60, 60, 35], "marks": [60, 60, 60, 60, 35],
                      "balls": [21, 20, 22, 36, 30], "gate": [True] * 5})
    o["ball_pct"] = o["balls"] / o["marks"]
    f = ss.usual_flags(o, min_pitches=40, z=2.0).set_index("game_idx")
    assert bool(f.loc[4, "ball_flag"])                          # 60% vs 평소 35% → 표시
    assert not f.loc[[1, 2, 3], "ball_flag"].any()
    assert not bool(f.loc[5, "ball_flag"])                      # 40구 미만은 판정하지 않음 (볼이 많아도)
    assert abs(f.loc[4, "usual"] - (21 + 20 + 22 + 30) / (60 * 3 + 35)) < 1e-9   # 평소 = 그 등판을 뺀 나머지 합
