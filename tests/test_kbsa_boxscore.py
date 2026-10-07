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
        + pitcher_table("가나고", [("홍길동", 17, "선발", "패", "2.1", 11, 29), ("나다라", 23, "교체", "-", "3", 14, 38), ("마바사", 11, "교체", "-", "1.2", 7, 24)])
        + pitcher_table("다라고", [("사아자", 54, "선발", "승", "7", 25, 101), ("차카타", 11, "교체", "-", "2", 5, 27)])
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
                     "innings": "2.1", "outs": 7, "batters": 11, "pitches": 29, "at_bats": 9, "hits": 2, "hr": 0, "bb_hbp": 1, "k": 3, "runs": 1, "er": 1}
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
    assert list(table.columns) == ["game_idx", "date", "team", "opponent", "name", "number", "role", "result", "innings", "outs", "batters", "pitches",
                                   "at_bats", "hits", "hr", "bb_hbp", "k", "runs", "er"]
    assert len(table) == 5 and table["date"].dtype.kind == "M"
    assert table.loc[table["team"] == "가나고", "opponent"].unique().tolist() == ["다라고"]
    assert table.loc[table["team"] == "다라고", "opponent"].unique().tolist() == ["가나고"]
    assert pd.api.types.is_integer_dtype(table["outs"]) and table["pitches"].sum() == 29 + 38 + 24 + 101 + 27


def test_empty_placeholder_rows_are_skipped():
    page = PAGE.replace(pitcher_table("다라고", [("사아자", 54, "선발", "승", "7", 25, 101), ("차카타", 11, "교체", "-", "2", 5, 27)]),
                        '<div class="section_sumrec"><h4>다라고 투수기록</h4><div class="sum_table"><table class="record_table" summary="투수기록"><tbody>'
                        '<tr><th>()</th><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td>-</td></tr>'
                        '</tbody></table></div></div>')
    rows = kb.parse_record_detail(page, game_idx=1)["pitchers"]
    assert [r["team"] for r in rows] == ["가나고"] * 3                               # 빈 자리표시 줄은 투수가 아니다


def batting_table(team, rows):
    """rows: [(타순, 포지션, 이름(번호), {이닝: 셀})]. 셀은 '중안/4구'처럼 타석을 /로, 타석 안 사건을 ,로 구분."""
    body = ""
    for slot, pos, who, cells in rows:
        inn = "".join(f"<td>{'<span>' + cells[i] + '</span>' if i in cells else ''}</td>" for i in range(1, 21))
        body += f"<tr><td>{slot}</td><td><span>{pos}</span></td><td>{who}</td>{inn}<td class=\"fixed\"></td><td class=\"fixed\">3</td><td class=\"fixed\">1</td><td class=\"fixed\">0</td><td class=\"fixed\">0</td><td class=\"fixed\">0.333</td></tr>"
    return f'<div class="section_sumrec"><h4>{team} 타자기록</h4><table class="record_table"><thead><tr><th>타순</th></tr></thead><tbody>{body}</tbody></table></div>'


BATTING = batting_table("다라고", [
    (1, "유격수", "가나(7)", {1: "삼진", 3: "중안/4구", 6: "2땅"}),
    (2, "1루수", "다라(8)", {1: "4구", 3: "사구", 4: "삼진", 7: "유플"}),
    (3, "포수", "마바(12)", {1: "우플", 3: "좌월2,폭투", 4: "유땅", 7: "삼진"}),
    (4, "3루수", "사아(10)", {1: "좌파플", 3: "3실", 4: "중안", 7: "중안"}),
    (5, "좌익수", "자차(3)", {2: "삼진", 3: "희플", 5: "병살"}),
    (6, "우익수", "카타(5)", {2: "2땅", 3: "삼진", 5: "4구"}),
    (7, "중견수", "파하(9)", {2: "좌안", 3: "유땅", 5: "좌플"}),
    (8, "2루수", "거너(2)", {2: "1땅", 3: "중안"}),
    (8, "대타", "더러(31)", {6: "삼진"}),
    (9, "지명타자", "머버(1)", {2: "삼진", 3: "좌플", 6: "삼진"}),
])


def test_batting_rows_keep_slot_and_inning_cells_without_names():
    rows = kb.parse_batting(BATTING)["다라고"]
    assert len(rows) == 10 and rows[0]["slot"] == 1 and rows[8]["slot"] == 8 and "name" not in rows[0]
    assert rows[0]["cells"][3] == "중안/4구" and rows[2]["cells"][3] == "좌월2,폭투" and 2 not in rows[0]["cells"]


def test_plate_appearances_follow_the_lineup_cycle_across_innings_and_split_double_cells():
    pas = kb.plate_appearances(kb.parse_batting(BATTING)["다라고"])
    seq = [(p["inning"], p["slot"], p["result"]) for p in pas]
    assert seq[:4] == [(1, 1, "삼진"), (1, 2, "4구"), (1, 3, "우플"), (1, 4, "좌파플")]
    assert seq[4:9] == [(2, 5, "삼진"), (2, 6, "2땅"), (2, 7, "좌안"), (2, 8, "1땅"), (2, 9, "삼진")]      # 2회는 5번부터
    third = [s for s in seq if s[0] == 3]
    assert [t[1] for t in third] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 1] and third[0][2] == "중안" and third[-1][2] == "4구"   # 타자 일순 뒤 1번 두 번째 타석
    assert [s for s in seq if s[0] == 4] == [(4, 2, "삼진"), (4, 3, "유땅"), (4, 4, "중안")]                 # 3회 마지막(1번) 다음인 2번부터
    assert [s for s in seq if s[0] == 6] == [(6, 8, "삼진"), (6, 9, "삼진"), (6, 1, "2땅")]                 # 8번 자리는 대타(둘째 줄)
    assert len(pas) == 31
    assert pas[2]["events"] == [] and next(p for p in pas if p["result"] == "좌월2")["events"] == ["폭투"]


def test_assignment_splits_the_sequence_by_batters_faced_and_rejects_a_mismatch():
    pas = kb.plate_appearances(kb.parse_batting(BATTING)["다라고"])
    parts = kb.assign_to_pitchers(pas, [9, 22])
    assert [len(x) for x in parts] == [9, 22] and parts[1][0]["inning"] == 3 and parts[1][0]["result"] == "중안"
    assert kb.assign_to_pitchers(pas, [9, 21]) is None                                     # 타자 수 합이 안 맞으면 재구성 불가


def test_result_categories():
    assert [kb.pa_category(r) for r in ["삼진", "4구", "고4구", "사구", "중안", "좌월2", "우중3", "좌월홈", "2땅", "유플", "좌파플", "3실", "희플", "희번", "야선", "병살", "직"]] == \
        ["K", "BB", "BB", "HBP", "H", "H", "H", "HR", "OUT", "OUT", "OUT", "E", "SAC", "SAC", "FC", "OUT", "OUT"]


def test_substitution_and_runner_markers_are_not_plate_appearances_and_events_may_precede_the_result():
    rows = [{"slot": 1, "cells": {1: "대타,삼진", 2: "폭투,4구", 3: "승부주자,주자아웃"}}, {"slot": 2, "cells": {1: "대수비", 2: "낫아웃+,폭투", 3: "대주자,도루"}},
            {"slot": 3, "cells": {1: "포구실책", 2: "투희번출,송구실책", 3: "3실"}}]
    pas = kb.plate_appearances(rows)
    # 1회는 1번만 타석(2·3번 칸은 교체 표시·사건뿐) → 2회는 2번부터: 2, 3, 1 순
    assert [(p["inning"], p["slot"], p["result"], p["events"]) for p in pas] == [
        (1, 1, "삼진", ["대타"]), (2, 2, "낫아웃+", ["폭투"]), (2, 3, "투희번출", ["송구실책"]), (2, 1, "4구", ["폭투"]), (3, 1, "승부주자", ["주자아웃"]), (3, 3, "3실", [])]
    assert [kb.pa_category(p["result"]) for p in pas] == ["K", "K", "SAC", "BB", "TB", "E"]


def test_tiebreak_runners_count_as_pseudo_plate_appearances_at_the_start_of_the_inning():
    rows = [{"slot": 1, "cells": {10: "승부주자"}}, {"slot": 2, "cells": {10: "승부주자,폭투"}}, {"slot": 3, "cells": {9: "삼진", 10: "중안"}}, {"slot": 4, "cells": {10: "4구"}}]
    pas = kb.plate_appearances(rows)
    # 9회 마지막 타자가 3번 → 10회는 승부주자 둘 다음 4번부터, 그다음 3번
    assert [(p["inning"], p["slot"], p["result"]) for p in pas] == [(9, 3, "삼진"), (10, 1, "승부주자"), (10, 2, "승부주자"), (10, 4, "4구"), (10, 3, "중안")]
    assert kb.pa_category("승부주자") == "TB" and pas[2]["events"] == ["폭투"]
