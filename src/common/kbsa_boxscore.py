"""KBSA 기록실 경기 기록 페이지(/game/record_detail?game_idx=…) 파서.

페이지 머리의 설명(meta description)에서 날짜·시각·구장·두 팀을, 팀마다 있는 '<팀> 투수기록' 표에서
투수별 등판 구분·이닝·타자·투구수를 읽는다. 실명이 들어 있으므로 이 결과는 data/ 밖으로 내보내지 않고,
등번호 표기로 바꾸는 변환(src/17_kbsa_records.py)을 거친 뒤에만 쓴다.
"""
from __future__ import annotations

import html
import re

import pandas as pd

RESULT_COLUMNS = ["at_bats", "hits", "hr", "bb_hbp", "k", "runs", "er"]                   # 투수 표의 타수·피안타·피홈런·4사구·삼진·실점·자책
ROW_COLUMNS = ["game_idx", "date", "team", "opponent", "name", "number", "role", "result", "innings", "outs", "batters", "pitches", *RESULT_COLUMNS]
_DESCRIPTION = re.compile(r'<meta name="description" content="(\d{4})\.(\d{2})\.(\d{2})/(\d{2}:\d{2}) (.+?) (\S+) vs (\S+)"')
_TITLE = re.compile(r'<meta property="og:title" content="([^"]*)"')
_SECTION = re.compile(r"<h4>([^<]+?) 투수기록</h4>(.*?)</table>", re.S)
_ROW = re.compile(r"<tr(?: class=\"(\w+)\")?>(.*?)</tr>", re.S)
_CELL = re.compile(r"<t[hd][^>]*>(.*?)</t[hd]>", re.S)
_NAME = re.compile(r"^(.*)\((\d+)\)$")


def _text(cell: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()


def _int(text: str) -> int | None:
    return int(text) if text.isdigit() else None


def outs_from_innings(innings: str) -> int:
    """'4.2' 같은 이닝 표기를 아웃 수로 바꾼다 (소수점 뒤는 0·1·2만 허용)."""
    whole, _, part = innings.partition(".")
    if not whole.isdigit() or part not in ("", "0", "1", "2"):
        raise ValueError(f"이닝 표기를 읽을 수 없음: {innings!r}")
    return int(whole) * 3 + int(part or 0)


def parse_record_detail(text: str, game_idx: int) -> dict:
    """한 경기 페이지 → {game_idx, date, time, venue, competition, teams, pitchers[]}."""
    head = _DESCRIPTION.search(text)
    if head is None:
        raise ValueError(f"경기 {game_idx}: 머리 정보(meta description)를 찾지 못함")
    y, m, d, time, venue, home, away = head.groups()
    title = _TITLE.search(text)
    pitchers = []
    for team, body in _SECTION.findall(text):
        for cls, row in _ROW.findall(body):
            cells = [_text(c) for c in _CELL.findall(row)]
            if cls == "sum" or len(cells) < 8 or cells[0] == "선수명" or not cells[5]:     # 합계·머리글·빈 자리표시('()' 줄)는 건너뛴다
                continue
            who = _NAME.match(cells[0])
            name, number = (who.group(1), int(who.group(2))) if who else (cells[0], None)
            pitchers.append({"team": html.unescape(team), "name": name, "number": number, "role": cells[1], "result": cells[2],
                             "innings": cells[5], "outs": outs_from_innings(cells[5]), "batters": _int(cells[6]), "pitches": _int(cells[7]),
                             **{col: _int(cells[8 + i]) if len(cells) > 8 + i else None for i, col in enumerate(RESULT_COLUMNS)}})
    return {"game_idx": game_idx, "date": f"{y}-{m}-{d}", "time": time, "venue": venue, "teams": [home, away],
            "competition": html.unescape(title.group(1)) if title else None, "pitchers": pitchers}


def games_to_rows(games: list[dict]) -> pd.DataFrame:
    """여러 경기의 투수 줄을 한 표로. 상대 팀은 같은 경기의 다른 팀."""
    rows = []
    for g in games:
        for p in g["pitchers"]:
            others = [t for t in g["teams"] if t != p["team"]]
            rows.append({"game_idx": g["game_idx"], "date": g["date"], "opponent": others[0] if len(others) == 1 else None, **p})
    table = pd.DataFrame(rows, columns=ROW_COLUMNS)
    table["date"] = pd.to_datetime(table["date"])
    for col in ["pitches", "batters", *RESULT_COLUMNS]:
        table[col] = table[col].astype("Int64")
    return table


# ---------- 타격표 → 타석 순서 → 투수 배정 (등판 흐름 재구성) ----------

_BAT_SECTION = re.compile(r"<h4>([^<]+?) 타자기록</h4>(.*?)</table>", re.S)
_BAT_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
INNINGS = 20


def parse_batting(text: str) -> dict[str, list[dict]]:
    """팀마다 타격표 줄 목록: {slot(타순), cells{이닝: 셀 글자}}. 선수 이름은 담지 않는다.
    셀 글자는 '중안/4구'(한 이닝 두 타석), '좌월2,폭투'(타석 결과와 그 뒤 사건)처럼 원문 그대로."""
    out: dict[str, list[dict]] = {}
    for team, body in _BAT_SECTION.findall(text):
        rows = []
        for row in _BAT_ROW.findall(body):
            cells = _CELL.findall(row)                       # 타순·포지션·이름은 <th>, 이닝 칸과 합계는 <td>
            if len(cells) < 3 + INNINGS:
                continue
            slot = _text(cells[0])
            if not slot.isdigit():
                continue
            inning_cells = {i + 1: _text(c) for i, c in enumerate(cells[3:3 + INNINGS]) if _text(c)}
            rows.append({"slot": int(slot), "cells": inning_cells})
        out[html.unescape(team)] = rows
    return out


_OUTCOME = re.compile(r"(안|땅|플|직|삼진|4구|사구|홈|야선|희|번|병살|삼중살|낫아웃|타격방해|주루방해|타자타구|쓰리번트|수비방해|루타|아웃)")
_NOT_OUTCOME = {"대타", "대수비", "대주자", "승부주자", "폭투", "보크", "포일", "도루", "도루자", "주자아웃", "견제사", "진루", "득점", "주자"}


def is_outcome(token: str) -> bool:
    """타석 결과 글자인가 (교체 표시·주루 사건은 아니다)."""
    if token in _NOT_OUTCOME or token.endswith("실책") or token.endswith("도루"):
        return False
    return bool(_OUTCOME.search(token)) or bool(re.search(r"(실|[23]|R)(\[[^\]]*\])?$", token))


def plate_appearances(rows: list[dict]) -> list[dict]:
    """타격표 줄들을 시간 순서의 타석 목록으로 편다: {inning, slot, result, events}.
    이닝 안의 순서는 직전 이닝 마지막 타자의 다음 타순부터 돌며, 한 타순에 두 타석('/')이면 일순 뒤에 다시 온다.
    같은 타순의 여러 줄(교체 선수)은 줄 순서대로 쓴다."""
    innings = sorted({i for r in rows for i in r["cells"]})
    slots = sorted({r["slot"] for r in rows})
    out, start = [], slots[0] if slots else 1
    for inning in innings:
        queue: dict[int, list[str]] = {}
        for r in rows:
            if inning in r["cells"]:
                for part in r["cells"][inning].split("/"):
                    tokens = [t.strip() for t in part.split(",") if t.strip()]
                    if tokens and tokens[0] == "승부주자":              # 연장 승부치기 주자: 협회는 투수의 '타자'에 넣는다 → 이닝 맨 앞의 유사 타석
                        out.append({"inning": inning, "slot": r["slot"], "result": "승부주자", "events": tokens[1:]})
                    elif any(is_outcome(t) for t in tokens):        # 결과 토큰이 없는 칸(대수비·대주자·단독 폭투)은 타석이 아니다
                        queue.setdefault(r["slot"], []).append(tokens)
        remaining = sum(len(q) for q in queue.values())
        order = slots[slots.index(start):] + slots[:slots.index(start)] if start in slots else slots
        i, last = 0, start
        while remaining:
            slot = order[i % len(order)]
            if queue.get(slot):
                tokens = queue[slot].pop(0)
                result = next(t for t in tokens if is_outcome(t))
                out.append({"inning": inning, "slot": slot, "result": result, "events": [t for t in tokens if t != result]})
                remaining -= 1
                last = slot
            i += 1
        start = order[(order.index(last) + 1) % len(order)] if order else start
    return out


def assign_to_pitchers(pas: list[dict], batters_faced: list[int]) -> list[list[dict]] | None:
    """타석 목록을 투수 순서(선발 → 교체)대로 각 투수의 '타자' 수만큼 잘라 준다. 합이 안 맞으면 None."""
    if sum(batters_faced) != len(pas):
        return None
    parts, pos = [], 0
    for n in batters_faced:
        parts.append(pas[pos:pos + n])
        pos += n
    return parts


def pa_category(result: str) -> str:
    """타석 결과 글자 → 범주: K 삼진 / BB 4구·고의4구 / HBP 사구 / HR 홈런 / H 안타·2루타·3루타 / SAC 희생 / E 실책 출루 / FC 야수선택 / OUT 나머지."""
    r = result
    if r == "승부주자":
        return "TB"
    if "삼진" in r or "낫아웃" in r or "쓰리번트" in r:
        return "K"
    if r.endswith("4구") or r == "4구":
        return "BB"
    if r == "사구":
        return "HBP"
    if "홈" in r:
        return "HR"
    if "희" in r:                                    # 희번·희플 (앞에 수비 위치가 붙기도: 투희번, 중희플, 3희번출)
        return "SAC"
    if r.endswith("안") or (len(r) >= 2 and r[-1] in "23"):
        return "H"
    if "실" in r:
        return "E"
    if "야선" in r:
        return "FC"
    return "OUT"
