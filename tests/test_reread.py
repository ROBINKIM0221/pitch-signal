"""기록지 다시 읽기 묶음 준비(다시 읽을 타석 고르기·묶음·타석 칸 그림) 테스트. 실행: python -m pytest -q tests/test_reread.py"""
import json

import numpy as np
import pandas as pd

from src.common import reread


def test_hard_outings_are_40_plus_pitches_that_failed_the_count_check_within_scope():
    o = pd.DataFrame({"game_idx": [1, 1, 2, 3], "team": ["A"] * 4, "number": [11, 12, 13, 14],
                      "pitches": [45, 39, 60, 70], "gate": [False, False, True, False]})
    assert reread.hard_outing_keys(o, {1, 2}, 40) == {(1, "A", 11)}        # 39구, 검산 통과, 범위 밖 경기는 빠진다


def test_mismatch_columns_take_a_difference_of_2_to_12_and_skip_doubtful_grids():
    rows = pd.DataFrame({"game_idx": [1, 1, 1, 1, 1, 2], "sheet": ["1_a", "1_a", "1_a", "1_a", "1_b", "2_c"],
                         "col": [3, 4, 5, 6, 3, 3], "pitches": [13, 10, 25, 0, 13, 13]})
    counts = {("1_a", 3): 10, ("1_a", 4): 9, ("1_a", 5): 12, ("1_a", 6): 5, ("1_b", 3): 10, ("2_c", 3): 10}
    marks = pd.DataFrame([{"sheet": s, "col": c, "pa": 0} for (s, c), n in counts.items() for _ in range(n)])
    meta = pd.DataFrame({"sheet": ["1_a", "1_b", "2_c"], "game_idx": [1, 1, 2], "hy": [0.9, 0.5, 0.9], "match": [0.9, 0.9, 0.9]})
    # 1_a 3열: 차 3 → 포함 / 4열: 차 1 / 5열: 차 13 / 6열: 줄 값 0 / 1_b: 격자 의심(hy 0.5) / 2_c: 범위 밖 경기
    assert reread.mismatch_columns(rows, marks, meta, {1}) == {("1_a", 3)}


def test_mismatch_columns_count_a_column_with_no_marks_as_zero():
    rows = pd.DataFrame({"game_idx": [1], "sheet": ["1_a"], "col": [2], "pitches": [5]})
    marks = pd.DataFrame({"sheet": ["1_a"], "col": [9], "pa": [0]})
    meta = pd.DataFrame({"sheet": ["1_a"], "game_idx": [1], "hy": [0.9], "match": [0.9]})
    assert reread.mismatch_columns(rows, marks, meta, {1}) == {("1_a", 2)}


def test_batch_names_sort_by_week_then_stage():
    names = [reread.batch_name(2027, "20270315", 1, 1), reread.batch_name(2027, "20270308", 2, 3), reread.batch_name(2027, "20270308", 1, 12)]
    assert sorted(names) == ["y27-20270308-s1-12", "y27-20270308-s2-03", "y27-20270315-s1-01"]


def pas():
    return [{"inning": 1, "slot": 1, "result": "삼진", "events": [], "pitcher": 17},
            {"inning": 1, "slot": 2, "result": "고의4구", "events": [], "pitcher": 17},
            {"inning": 1, "slot": 3, "result": "좌안", "events": []},                      # 투수를 못 정한 타석
            {"inning": 2, "slot": 4, "result": "유땅", "events": [], "pitcher": 23}]


def test_items_for_sheet_use_the_2026_item_format():
    items = reread.items_for_sheet("5_9", 5, "나팀", pas(), lambda p, cell: True)
    assert items[0] == {"id": "5_9_0", "sheet": "5_9", "pa": 0, "mode": "pa", "inning": 1, "col": 1, "slot": 1, "result": "삼진",
                        "game_idx": 5, "team": "나팀", "number": 17, "cat": "K", "ibb": False, "blobs": [{"idx": 0, "model": "-"}]}
    assert [it["id"] for it in items] == ["5_9_0", "5_9_1", "5_9_3"]                       # 투수 없는 타석은 빠지고 번호는 원래 순서 그대로
    assert items[1]["result"] == "4구" and items[1]["ibb"] is True
    assert (items[2]["col"], items[2]["slot"], items[2]["number"]) == (2, 4, 23)


def test_items_for_sheet_keep_only_the_wanted_plate_appearances():
    items = reread.items_for_sheet("5_9", 5, "나팀", pas(), lambda p, cell: cell[0] == 2)
    assert [it["id"] for it in items] == ["5_9_3"]


def item(i):
    return {"id": f"s_{i}", "sheet": "s", "pa": i}


def test_write_batches_puts_60_in_a_batch_and_never_repeats_a_plate_appearance(tmp_path):
    names = reread.write_batches([item(i) for i in range(130)], tmp_path, 2027, "20270308", 1)
    assert names == ["y27-20270308-s1-01", "y27-20270308-s1-02", "y27-20270308-s1-03"]
    assert [len(json.loads((tmp_path / n / "items.json").read_text(encoding="utf-8"))) for n in names] == [60, 60, 10]
    assert reread.already_planned(tmp_path) == {f"s_{i}" for i in range(130)}
    again = reread.write_batches([item(i) for i in range(125, 135)], tmp_path, 2027, "20270315", 2)   # 5개만 새 타석
    assert again == ["y27-20270315-s2-01"]
    assert [it["id"] for it in json.loads((tmp_path / again[0] / "items.json").read_text(encoding="utf-8"))] == [f"s_{i}" for i in range(130, 135)]
    assert reread.write_batches([item(1)], tmp_path, 2027, "20270322", 1) == []


def test_finished_needs_a_reading_for_every_item(tmp_path):
    reread.write_batches([item(i) for i in range(3)], tmp_path, 2027, "20270308", 1)
    b = tmp_path / "y27-20270308-s1-01"
    assert reread.finished(b) is False
    (b / "first_pass.json").write_text(json.dumps({"s_0": ["BS"], "s_1": [""]}), encoding="utf-8")
    assert reread.finished(b) is False
    (b / "first_pass.json").write_text(json.dumps({"s_0": ["BS"], "s_1": [""], "s_2": ["S?"]}), encoding="utf-8")
    assert reread.finished(b) is True


def grid():
    """칸 두 열·두 행. Xr[행] = [띠 왼쪽, 띠 오른쪽(본문 왼쪽), 칸 오른쪽, …], Yc[열] = 행 경계."""
    return {"Xr": [[100, 120, 200, 220, 300], [100, 120, 200, 220, 300]], "Yc": [[50, 110, 170], [50, 110, 170]]}


def test_tile_shows_the_cell_three_times_larger_with_room_on_the_left_and_a_blue_box():
    im = np.full((300, 400, 3), 255, np.uint8)
    t = reread.tile(im, grid(), 0, 0)                               # 첫 열 첫 행: x 100~200, y 50~110
    assert t.size == ((204 - 80) * 3, (128 - 32) * 3)               # 왼쪽 20px·오른쪽 4px, 위아래로 칸 높이의 0.3배
    assert t.getpixel(((100 - 80) * 3, (50 - 32) * 3 + 30)) == (0, 90, 255)   # 이 타석 칸의 왼쪽 변


def test_tile_is_clipped_at_the_edge_of_the_photo():
    im = np.full((120, 205, 3), 255, np.uint8)
    g = {"Xr": [[10, 30, 200]], "Yc": [[5, 100]]}
    assert reread.tile(im, g, 0, 0).size == (204 * 3, 120 * 3)      # 왼쪽 0에서, 아래는 사진 끝에서 잘림


def test_pages_hold_twenty_tiles_each_in_five_columns():
    im = np.full((300, 400, 3), 255, np.uint8)
    items = [{"id": f"s_{i}", "result": "삼진", "inning": 1} for i in range(45)]
    tiles = [reread.tile(im, grid(), 0, 0) for _ in items]
    pages = reread.pages(items, tiles)
    assert len(pages) == 3
    cw, ch = tiles[0].width + 6, tiles[0].height + 30
    assert pages[0].size == (cw * 5, ch * 4) and pages[2].size == (cw * 5, ch * 1)


def two_batches(tmp_path):
    """묶음 둘: 첫째는 판독이 끝났고 그림이 남아 있다, 둘째는 아직이고 그림이 있다."""
    reread.write_batches([item(i) for i in range(61)], tmp_path, 2027, "20270308", 1)
    a, b = tmp_path / "y27-20270308-s1-01", tmp_path / "y27-20270308-s1-02"
    (a / "first_pass.json").write_text(json.dumps({f"s_{i}": ["B"] for i in range(60)}), encoding="utf-8")
    for d in (a, b):
        (d / "tiles").mkdir()
        (d / "tiles" / "x.png").write_bytes(b"x")
        (d / "sheet_01.png").write_bytes(b"x")
    (a / "zoom.png").write_bytes(b"x")
    return a, b


def test_status_counts_finished_pending_and_rendered(tmp_path):
    two_batches(tmp_path)
    assert reread.status(tmp_path) == {"total": 2, "finished": 1, "pending": 1, "rendered": 2}
    assert reread.status(tmp_path / "none") == {"total": 0, "finished": 0, "pending": 0, "rendered": 0}


def test_clean_removes_pictures_of_finished_batches_only(tmp_path):
    a, b = two_batches(tmp_path)
    assert reread.clean(tmp_path) == 1
    assert not (a / "tiles").exists() and not (a / "sheet_01.png").exists() and not (a / "zoom.png").exists()
    assert (a / "items.json").exists() and (a / "first_pass.json").exists()
    assert (b / "tiles" / "x.png").exists() and (b / "sheet_01.png").exists()


def test_to_render_lists_unfinished_batches_without_pictures_in_name_order(tmp_path):
    a, b = two_batches(tmp_path)
    reread.write_batches([item(i) for i in range(100, 103)], tmp_path, 2027, "20270315", 1)
    (b / "sheet_01.png").unlink()
    assert [p.name for p in reread.to_render(tmp_path)] == ["y27-20270308-s1-02", "y27-20270315-s1-01"]


def test_planning_twice_with_the_same_tag_never_reuses_a_batch_name(tmp_path):
    first = reread.write_batches([item(i) for i in range(61)], tmp_path, 2027, "20270308", 1)
    (tmp_path / first[0] / "first_pass.json").write_text(json.dumps({f"s_{i}": ["B"] for i in range(60)}), encoding="utf-8")
    before = [(tmp_path / n / "items.json").read_text(encoding="utf-8") for n in first]
    second = reread.write_batches([item(i) for i in range(100, 103)], tmp_path, 2027, "20270308", 1)     # 같은 날 다시 계획
    assert second == ["y27-20270308-s1-03"]
    assert [(tmp_path / n / "items.json").read_text(encoding="utf-8") for n in first] == before          # 앞 묶음은 그대로
    assert reread.finished(tmp_path / first[0]) is True
