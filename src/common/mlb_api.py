"""MLB Stats API 호출 보조 함수 (선수 이동 기록, 선수 정보, 경기별 구장)."""
from __future__ import annotations

import calendar
import time
from datetime import date

import pandas as pd
import requests

BASE = "https://statsapi.mlb.com/api/v1"


def month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """start~end를 달력 월 단위 (첫날, 끝날) 목록으로 나눈다. 마지막 달은 end에서 자른다."""
    out = []
    while start <= end:
        last = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        out.append((start, min(last, end)))
        start = date(start.year + start.month // 12, start.month % 12 + 1, 1)
    return out


def chunks(items: list, n: int) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


def get_json(url: str, params: dict, pause: float, retries: int, timeout: float, get=requests.get) -> dict:
    """GET 한 번. 실패하면 pause초 쉬고 retries번까지 다시 시도한다. 성공한 뒤에도 pause초 쉰다."""
    for attempt in range(retries + 1):
        try:
            r = get(url, params=params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            time.sleep(pause)
            return data
        except Exception:
            if attempt == retries:
                raise
            time.sleep(pause)


def flatten_transaction(t: dict) -> dict:
    person, team = t.get("person") or {}, t.get("toTeam") or {}
    return {"id": t.get("id"), "person_id": person.get("id"), "person_name": person.get("fullName"),
            "to_team": team.get("name"), "date": t.get("date"), "effective_date": t.get("effectiveDate"),
            "resolution_date": t.get("resolutionDate"), "type_code": t.get("typeCode"),
            "type_desc": t.get("typeDesc"), "description": t.get("description")}


def flatten_person(p: dict) -> dict:
    return {"id": p.get("id"), "full_name": p.get("fullName"), "birth_date": p.get("birthDate"),
            "pitch_hand": (p.get("pitchHand") or {}).get("code")}


def _api_options(cfg: dict) -> dict:
    a = cfg["data"]["api"]
    return {"pause": a["pause_sec"], "retries": a["retries"], "timeout": a["timeout_sec"]}


def fetch_transactions(cfg: dict, get=requests.get) -> pd.DataFrame:
    """설정 기간의 선수 이동 기록을 한 달씩 불러 한 표로 돌려준다."""
    tx = cfg["data"]["transactions"]
    rows = []
    for first, last in month_ranges(date.fromisoformat(tx["start"]), date.fromisoformat(tx["end"])):
        params = {"sportId": tx["sport_id"], "startDate": str(first), "endDate": str(last)}
        data = get_json(f"{BASE}/transactions", params, get=get, **_api_options(cfg))
        rows += [flatten_transaction(t) for t in data.get("transactions", [])]
    return pd.DataFrame(rows)


def fetch_people(ids, cfg: dict, get=requests.get) -> pd.DataFrame:
    """선수 ID들의 이름·생년월일·투구하는 손을 묶음 단위로 불러 한 표로 돌려준다."""
    rows = []
    for batch in chunks(sorted(set(ids)), cfg["data"]["api"]["people_batch"]):
        params = {"personIds": ",".join(str(i) for i in batch)}
        data = get_json(f"{BASE}/people", params, get=get, **_api_options(cfg))
        rows += [flatten_person(p) for p in data.get("people", [])]
    return pd.DataFrame(rows)


def fetch_venues(cfg: dict, get=requests.get) -> pd.DataFrame:
    """설정의 시즌마다 경기 일정을 불러 경기별 구장(game_pk, venue_id, venue_name)을 돌려준다. 한 경기는 한 줄."""
    data_cfg = cfg["data"]
    rows = []
    for season in data_cfg["seasons"]:
        params = {"sportId": data_cfg["transactions"]["sport_id"], "season": season, "gameType": data_cfg["game_type"]}
        data = get_json(f"{BASE}/schedule", params, get=get, **_api_options(cfg))
        for day in data.get("dates", []):
            for game in day.get("games", []):
                venue = game.get("venue") or {}
                rows.append({"game_pk": game.get("gamePk"), "venue_id": venue.get("id"), "venue_name": venue.get("name")})
    return pd.DataFrame(rows).drop_duplicates("game_pk", ignore_index=True)
