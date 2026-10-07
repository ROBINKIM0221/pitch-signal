"""KBSA 기록실 경기 기록 페이지(record_detail) 파서 테스트. 실행: python -m pytest -q tests/test_kbsa_boxscore.py
표본 HTML은 실제 페이지와 같은 구조에 지어낸 학교·선수 이름을 넣은 것이다."""
import pandas as pd
import pytest

from src.common import kbsa_boxscore as kb


def pitcher_table(team, rows):
    body = "".join(
        f"<tr><th>{name}({num})</th><td>{role}</td><td>{res}</td><td>0</td><td>0</td><td>{ip}</td><td>{bf}</td><td>{np_}</td>"
        f"<td>9</td><td>2</td><td>0</td><td>1</td><td>3</td><td>1</td><td>1</td><td>2.00</td></tr>"
        for name, num, role, res, ip, bf, np_ in rows)
    return (f'<div class="section_sumrec"><h4>{team} 타자기록</h4><table><tr><th>타순</th></tr></table></div>'
            f'<div class="section_sumrec"><h4>{team} 투수기록</h4><div class="sum_table">'
            '<table class="record_table" summary="투수기록"><thead><tr><th>선수명</th><th>등판</th><th>결과</th><th>승</th><th>패</th>'
            '<th>이닝</th><th>타자</th><th>투구수</th><th>타수</th><th>피안타</th><th>피홈런</th><th>4사구</th><th>삼진</th><th>실점</th><th>자책</th><th>평균<br />자책점</th></tr></thead>'
            f'<tbody>{body}<tr class="sum"><th><span>합계</span></th><td></td><td></td><td></td><th><span>합계</span></th>'
            '<td class="score">9</td><td class="score">40</td><td class="score">150</td></tr></tbody></table></div></div>')


PAGE = ('<html><head><meta name="description" content="2025.10.17/09:00 어느 구장 보조2구장 가나고 vs 다라고" />'
        '<meta property="og:title" content="제1회 가상대회(18세 이하부)"/></head><body>'
        + pitcher_table("가나고", [("홍길동", 17, "선발", "패", "2.1", 11, 29), ("김철수", 23, "교체", "-", "3", 14, 38), ("이영희", 11, "교체", "-", "1.2", 7, 24)])
        + pitcher_table("다라고", [("박민수", 54, "선발", "승", "7", 25, 101), ("최지우", 11, "교체", "-", "2", 5, 27)])
        + "</body></html>")


def test_header_gives_date_time_venue_competition_and_both_teams():
    game = kb.parse_record_detail(PAGE, game_idx=1)
    assert game["game_idx"] == 1 and game["date"] == "2025-10-17" and game["time"] == "09:00"
    assert game["venue"] == "어느 구장 보조2구장" and game["teams"] == ["가나고", "다라고"]
    assert game["competition"] == "제1회 가상대회(18세 이하부)"


def test_each_pitcher_row_has_team_name_number_role_outs_batters_and_pitches():
    rows = kb.parse_record_detail(PAGE, game_idx=1)["pitchers"]
    assert len(rows) == 5                                            # 합계 줄은 빠진다
    first = rows[0]
    assert first == {"team": "가나고", "name": "홍길동", "number": 17, "role": "선발", "result": "패",
                     "innings": "2.1", "outs": 7, "batters": 11, "pitches": 29}
    assert [r["outs"] for r in rows] == [7, 9, 5, 21, 6]             # 2.1 → 7, 3 → 9, 1.2 → 5, 7 → 21, 2 → 6
    assert rows[3]["team"] == "다라고" and rows[3]["result"] == "승"


def test_blank_pitch_count_becomes_missing_not_zero():
    page = PAGE.replace("<td>29</td>", "<td></td>", 1)
    rows = kb.parse_record_detail(page, game_idx=1)["pitchers"]
    assert rows[0]["pitches"] is None and rows[1]["pitches"] == 38


def test_outs_rejects_malformed_innings():
    assert kb.outs_from_innings("4.2") == 14 and kb.outs_from_innings("0") == 0 and kb.outs_from_innings("0.1") == 1
    with pytest.raises(ValueError):
        kb.outs_from_innings("4.3")


def test_games_to_rows_puts_both_teams_outings_in_one_table_with_opponent():
    games = [kb.parse_record_detail(PAGE, game_idx=1)]
    table = kb.games_to_rows(games)
    assert list(table.columns) == ["game_idx", "date", "team", "opponent", "name", "number", "role", "result", "innings", "outs", "batters", "pitches"]
    assert len(table) == 5 and table["date"].dtype.kind == "M"
    assert table.loc[table["team"] == "가나고", "opponent"].unique().tolist() == ["다라고"]
    assert table.loc[table["team"] == "다라고", "opponent"].unique().tolist() == ["가나고"]
    assert pd.api.types.is_integer_dtype(table["outs"]) and table["pitches"].sum() == 29 + 38 + 24 + 101 + 27
