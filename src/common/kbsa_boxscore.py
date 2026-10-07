"""KBSA 기록실 경기 기록 페이지(/game/record_detail?game_idx=…) 파서.

페이지 머리의 설명(meta description)에서 날짜·시각·구장·두 팀을, 팀마다 있는 '<팀> 투수기록' 표에서
투수별 등판 구분·이닝·타자·투구수를 읽는다. 실명이 들어 있으므로 이 결과는 data/ 밖으로 내보내지 않고,
가명 처리(src/17_kbsa_tournament.py)를 거친 뒤에만 쓴다.
"""
from __future__ import annotations

import html
import re

import pandas as pd

ROW_COLUMNS = ["game_idx", "date", "team", "opponent", "name", "number", "role", "result", "innings", "outs", "batters", "pitches"]
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
            if cls == "sum" or len(cells) < 8 or cells[0] == "선수명":
                continue
            who = _NAME.match(cells[0])
            name, number = (who.group(1), int(who.group(2))) if who else (cells[0], None)
            pitchers.append({"team": html.unescape(team), "name": name, "number": number, "role": cells[1], "result": cells[2],
                             "innings": cells[5], "outs": outs_from_innings(cells[5]), "batters": _int(cells[6]), "pitches": _int(cells[7])})
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
    table["pitches"] = table["pitches"].astype("Int64")
    table["batters"] = table["batters"].astype("Int64")
    return table
