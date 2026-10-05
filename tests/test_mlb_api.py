"""MLB Stats API 보조 함수 테스트. 실행: python -m pytest -q"""
from datetime import date

import pytest

from src.common import mlb_api as api


def test_month_ranges_cover_each_calendar_month():
    assert api.month_ranges(date(2021, 1, 1), date(2021, 3, 15)) == [
        (date(2021, 1, 1), date(2021, 1, 31)),
        (date(2021, 2, 1), date(2021, 2, 28)),
        (date(2021, 3, 1), date(2021, 3, 15)),          # 마지막 달은 끝 날짜에서 자름
    ]


def test_chunks_split_ids_into_batches():
    assert api.chunks([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]


def test_flatten_transaction_keeps_the_fields_needed_for_il_labels():
    text = "Mets placed RHP A B on the 15-day injured list retroactive to June 9, 2025. Right elbow sprain."
    t = {"id": 7, "person": {"id": 660271, "fullName": "A B"}, "toTeam": {"id": 121, "name": "Mets"},
         "date": "2025-06-10", "effectiveDate": "2025-06-09", "typeCode": "SC", "typeDesc": "Status Change",
         "description": text}
    assert api.flatten_transaction(t) == {
        "id": 7, "person_id": 660271, "person_name": "A B", "to_team": "Mets", "date": "2025-06-10",
        "effective_date": "2025-06-09", "resolution_date": None, "type_code": "SC",
        "type_desc": "Status Change", "description": text}


def test_flatten_transaction_tolerates_missing_person_and_team():
    row = api.flatten_transaction({"id": 8, "date": "2025-06-10", "typeCode": "SC"})
    assert row["person_id"] is None and row["to_team"] is None and row["description"] is None


def test_flatten_person_keeps_birth_date_and_throwing_hand():
    p = {"id": 1, "fullName": "A B", "birthDate": "1995-01-02", "pitchHand": {"code": "R", "description": "Right"}}
    assert api.flatten_person(p) == {"id": 1, "full_name": "A B", "birth_date": "1995-01-02", "pitch_hand": "R"}


class _Resp:
    def __init__(self, payload=None):
        self.payload = {"ok": True} if payload is None else payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


CFG = {"data": {"transactions": {"start": "2021-01-01", "end": "2021-02-28", "sport_id": 1},
                "api": {"pause_sec": 0, "retries": 0, "timeout_sec": 1, "people_batch": 2}}}


def test_fetch_transactions_asks_month_by_month_and_flattens_rows():
    seen = []

    def get(url, params, timeout):
        seen.append((url.rsplit("/", 1)[-1], params["startDate"], params["endDate"], params["sportId"]))
        return _Resp({"transactions": [{"id": len(seen), "date": params["startDate"]}]})

    df = api.fetch_transactions(CFG, get=get)
    assert seen == [("transactions", "2021-01-01", "2021-01-31", 1), ("transactions", "2021-02-01", "2021-02-28", 1)]
    assert list(df["id"]) == [1, 2]
    assert list(df["date"]) == ["2021-01-01", "2021-02-01"]


def test_fetch_people_asks_for_sorted_ids_in_batches():
    seen = []

    def get(url, params, timeout):
        seen.append(params["personIds"])
        return _Resp({"people": [{"id": int(i), "fullName": "x"} for i in params["personIds"].split(",")]})

    df = api.fetch_people([3, 1, 2, 3], CFG, get=get)
    assert seen == ["1,2", "3"]
    assert list(df["id"]) == [1, 2, 3]


def test_get_json_retries_until_it_succeeds():
    calls = []

    def get(url, params, timeout):
        calls.append(url)
        if len(calls) < 3:
            raise ConnectionError("끊김")
        return _Resp()

    assert api.get_json("u", {}, pause=0, retries=3, timeout=1, get=get) == {"ok": True}
    assert len(calls) == 3


def test_get_json_gives_up_after_the_allowed_retries():
    calls = []

    def get(url, params, timeout):
        calls.append(url)
        raise ConnectionError("끊김")

    with pytest.raises(ConnectionError):
        api.get_json("u", {}, pause=0, retries=3, timeout=1, get=get)
    assert len(calls) == 4          # 첫 시도 1번 + 재시도 3번


def test_fetch_venues_asks_season_by_season_and_keeps_one_row_per_game():
    seen = []

    def get(url, params, timeout):
        seen.append((url.rsplit("/", 1)[-1], params["season"], params["sportId"], params["gameType"]))
        first = {"gamePk": 10 * params["season"], "venue": {"id": 5, "name": "A Park"}}
        other = {"gamePk": 10 * params["season"] + 1, "venue": {"id": 6, "name": "B Field"}}
        return _Resp({"dates": [{"games": [first, other]}, {"games": [first]}]})      # 중단됐다 이어진 경기는 두 번 나온다

    cfg = {"data": {**CFG["data"], "seasons": [2021, 2022], "game_type": "R"}}
    df = api.fetch_venues(cfg, get=get)
    assert seen == [("schedule", 2021, 1, "R"), ("schedule", 2022, 1, "R")]
    assert df.to_dict("list") == {"game_pk": [20210, 20211, 20220, 20221], "venue_id": [5, 6, 5, 6],
                                  "venue_name": ["A Park", "B Field", "A Park", "B Field"]}
