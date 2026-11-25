"""주간 갱신 데이터셋 변환(17_kbsa_records): 해석할 수 없는 페이지나 입력 검사에 걸린 경기 하나가 시즌 전체를 세우지 않는다."""
import importlib

import pandas as pd
import pytest

from src.common import hs_records as hr
from tests.test_kbsa_boxscore import pitcher_table

HEAD = ('<html><head><meta name="description" content="2025.10.{day}/09:00 어느 구장 보조2구장 가나고 vs 다라고" />'
        '<meta property="og:title" content="제1회 가상대회(18세 이하부)"/></head><body>')


def page(pitches: int, day: int) -> str:
    return (HEAD.format(day=day) + pitcher_table("가나고", [("홍길동", 17, "선발", "패", "9", 30, pitches)])
            + pitcher_table("다라고", [("사아자", 54, "선발", "승", "9", 30, 101)]) + "</body></html>")


RULES = {**hr.datasets_config()[1]["korea_2026"][1], "season": 2025, "competitions": ["기타"]}      # 실제 시즌 규칙에 연도·대회만 가짜 경기에 맞춤


DATASET = {"mode": "season", "name": "시험", "short": "시험", "season": 2025, "games_csv": "games.csv", "region_leagues": {}, "competitions": {},
           "competition_default": "기타", "overrides": {"competitions": ["기타"]}}


@pytest.fixture
def m17(tmp_path, monkeypatch):
    m = importlib.import_module("src.17_kbsa_records")
    for name in ("RAW", "PROCESSED", "TABLES"):
        (tmp_path / name).mkdir()
        monkeypatch.setattr(m, name, tmp_path / name)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(m, "SHEET_PITCHING", tmp_path / "none.csv")
    pd.DataFrame({"game_idx": [1, 2, 3], "date": "2025-10-17", "league": "제1회 가상대회", "lig_idx": 9, "team1": "가나고", "team2": "다라고"}).to_csv(tmp_path / "games.csv", index=False, encoding="utf-8-sig")
    (tmp_path / "RAW" / "record_detail_1.html").write_text(page(88, 10), encoding="utf-8")
    (tmp_path / "RAW" / "record_detail_2.html").write_text(page(250, 17), encoding="utf-8")                  # 투구 수가 범위 밖
    (tmp_path / "RAW" / "record_detail_3.html").write_text("<html><body>점검 중입니다</body></html>", encoding="utf-8")   # 기록 페이지가 아님
    return m


def test_live_season_drops_only_the_bad_games_and_lists_them(m17, tmp_path):
    out = m17.convert("korea_test", {"games_csv": "games.csv"}, {**DATASET, "live": True}, RULES)
    rows = pd.read_parquet(tmp_path / "PROCESSED" / "hs_korea_test_rows.parquet")
    assert out is not None and set(rows["game_idx"]) == {1}
    held = pd.read_csv(tmp_path / "PROCESSED" / "hs_korea_test_quarantine.csv", encoding="utf-8-sig")
    assert set(held["game_idx"]) == {2, 3} and set(held.loc[held["game_idx"] == 3, "kind"]) == {"기록 페이지"}


def test_the_list_of_held_games_goes_away_when_every_game_is_fine(m17, tmp_path):
    m17.convert("korea_test", {"games_csv": "games.csv"}, {**DATASET, "live": True}, RULES)
    for g, day in ((2, 17), (3, 24)):
        (tmp_path / "RAW" / f"record_detail_{g}.html").write_text(page(90, day), encoding="utf-8")
    m17.convert("korea_test", {"games_csv": "games.csv"}, {**DATASET, "live": True}, RULES)
    assert not (tmp_path / "PROCESSED" / "hs_korea_test_quarantine.csv").exists()
    assert set(pd.read_parquet(tmp_path / "PROCESSED" / "hs_korea_test_rows.parquet")["game_idx"]) == {1, 2, 3}


def test_a_dataset_that_is_not_live_still_stops_on_a_bad_page(m17):
    with pytest.raises((SystemExit, ValueError)):
        m17.convert("korea_test", {"games_csv": "games.csv"}, DATASET, RULES)
