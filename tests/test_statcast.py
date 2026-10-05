"""Statcast 내려받기 보조 함수 테스트. 실행: python -m pytest -q"""
from datetime import date

import numpy as np
import pandas as pd

from src.common import statcast as st


def test_week_ranges_splits_into_seven_day_chunks():
    weeks = st.week_ranges(date(2021, 4, 5), date(2021, 4, 19))
    assert weeks == [(date(2021, 4, 5), date(2021, 4, 11)),
                     (date(2021, 4, 12), date(2021, 4, 18)),
                     (date(2021, 4, 19), date(2021, 4, 19))]      # 마지막 주는 끝 날짜에서 자름


def test_season_window_comes_from_config():
    cfg = {"data": {"download_window": {"start": "03-15", "end": "10-05"}}}
    assert st.season_window(cfg, 2023) == (date(2023, 3, 15), date(2023, 10, 5))


def test_week_file_is_named_by_season_and_start_day(tmp_path):
    assert st.week_path(tmp_path, date(2021, 4, 5)) == tmp_path / "2021" / "0405.parquet"


def test_keep_game_type_drops_other_game_types():
    df = pd.DataFrame({"game_type": ["R", "S", "R", "W"], "pitcher": [1, 2, 3, 4]})
    assert list(st.keep_game_type(df, "R").pitcher) == [1, 3]


def _fake_week(start, end):
    return pd.DataFrame({"game_type": ["R", "S", "R"], "pitcher": [1, 2, 3], "game_date": [str(start)] * 3})


def test_download_weeks_saves_regular_season_rows_and_skips_existing_files(tmp_path):
    weeks = st.week_ranges(date(2021, 4, 5), date(2021, 4, 18))
    calls = []

    def fetch(start, end):
        calls.append(start)
        return _fake_week(start, end)

    first = st.download_weeks(weeks, tmp_path, fetch, "R")
    second = st.download_weeks(weeks, tmp_path, fetch, "R")
    saved = pd.read_parquet(tmp_path / "2021" / "0405.parquet")
    assert list(saved.pitcher) == [1, 3]
    assert first["saved"] == [w[0] for w in weeks] and first["failed"] == []
    assert second["skipped"] == [w[0] for w in weeks]
    assert len(calls) == 2                      # 두 번째 실행은 다시 받지 않음


def test_download_weeks_treats_empty_response_as_failure(tmp_path):
    weeks = st.week_ranges(date(2021, 4, 5), date(2021, 4, 11))
    result = st.download_weeks(weeks, tmp_path, lambda s, e: pd.DataFrame(), "R")
    assert result["failed"] == [date(2021, 4, 5)]
    assert not (tmp_path / "2021" / "0405.parquet").exists()     # 빈 응답을 '받음'으로 남기지 않음


def test_download_weeks_continues_after_a_week_fails(tmp_path):
    weeks = st.week_ranges(date(2021, 4, 5), date(2021, 4, 18))

    def fetch(start, end):
        if start == date(2021, 4, 5):
            raise ConnectionError("끊김")
        return _fake_week(start, end)

    result = st.download_weeks(weeks, tmp_path, fetch, "R")
    assert result["failed"] == [date(2021, 4, 5)]
    assert result["saved"] == [date(2021, 4, 12)]


TWO_WEEKS = {"data": {"download_window": {"start": "04-05", "end": "04-18"}, "game_type": "R"}}


def test_download_seasons_retries_failed_weeks_once_at_the_end(tmp_path):
    attempts = {}

    def fetch(start, end):
        attempts[start] = attempts.get(start, 0) + 1
        if start == date(2021, 4, 5) and attempts[start] == 1:
            raise ConnectionError("끊김")
        return _fake_week(start, end)

    summary = st.download_seasons(TWO_WEEKS, [2021, 2022], tmp_path, fetch)
    assert summary["failed"] == []
    assert attempts[date(2021, 4, 5)] == 2
    assert (tmp_path / "2021" / "0405.parquet").exists()
    assert [(s["season"], s["weeks"], s["rows"]) for s in summary["seasons"]] == [(2021, 1, 2), (2022, 2, 4)]


def test_download_seasons_lists_weeks_that_fail_twice(tmp_path):
    def fetch(start, end):
        raise ConnectionError("끊김")

    summary = st.download_seasons(TWO_WEEKS, [2021], tmp_path, fetch)
    assert summary["failed"] == [date(2021, 4, 5), date(2021, 4, 12)]


def test_missing_rates_counts_nan_share_per_column():
    df = pd.DataFrame({"release_speed": [90.0, np.nan, 92.0, 93.0], "zone": [1, 2, 3, 4]})
    rates = st.missing_rates(df, ["release_speed", "zone", "arm_angle"])
    assert rates["release_speed"] == 0.25
    assert rates["zone"] == 0.0
    assert np.isnan(rates["arm_angle"])        # 열 자체가 없으면 0이 아니라 결측으로 표시
