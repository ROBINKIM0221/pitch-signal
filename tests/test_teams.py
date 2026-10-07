"""팀 불펜 현황판(화면 4) 자료 테스트. 실행: python -m pytest -q tests/test_teams.py"""
import numpy as np
import pandas as pd

from src.common import teams as tm


def test_team_of_outing_uses_the_half_inning_to_tell_which_club_the_pitcher_threw_for():
    raw = pd.DataFrame({"pitcher": [1, 1, 2, 2, 3], "game_pk": [100, 100, 100, 100, 101],
                        "home_team": ["NYY", "NYY", "NYY", "NYY", "LAD"], "away_team": ["BOS", "BOS", "BOS", "BOS", "SD"],
                        "inning_topbot": ["Top", "Top", "Bot", "Bot", "Bot"]})
    out = tm.team_of_outing(raw)
    assert list(out.columns) == ["pitcher", "game_pk", "team"] and len(out) == 3
    assert dict(zip(zip(out["pitcher"], out["game_pk"]), out["team"])) == {(1, 100): "NYY", (2, 100): "BOS", (3, 101): "SD"}


def outings():
    rows = [(1, "2024-04-01", 1, 18), (1, "2024-04-02", 2, 12), (1, "2024-04-05", 3, 25), (2, "2024-04-01", 1, 30), (2, "2024-04-05", 3, 9), (9, "2024-04-01", 1, 95)]
    o = pd.DataFrame(rows, columns=["pitcher", "game_date", "game_pk", "n_all"])
    o["game_date"] = pd.to_datetime(o["game_date"]); o["season"] = 2024
    o["role"] = o["pitcher"].map({1: "RP", 2: "RP", 9: "SP"}); o["is_start"] = o["pitcher"] == 9
    return o


def test_team_payload_lists_relievers_with_their_outings_alarms_il_and_limit():
    o = outings()
    team_map = pd.DataFrame({"pitcher": [1, 1, 1, 2, 2, 9], "game_pk": [1, 2, 3, 1, 3, 1], "team": "NYY"})
    alarms = pd.DataFrame({"pitcher": [1], "season": [2024], "game_pk": [3], "velo_alarm": [True], "change_alarm": [False]})
    labels = pd.DataFrame({"pitcher": [2], "season": [2024], "part": ["elbow"], "il_date": pd.to_datetime(["2024-04-20"])})
    limits = pd.Series({(1, 2024): 40.0, (2, 2024): np.nan})
    names = pd.Series({1: "A Reliever", 2: "B Reliever", 9: "C Starter"})
    pay = tm.team_payload("NYY", 2024, o, team_map, alarms, labels, names, limits)
    assert pay["team"] == "NYY" and pay["season"] == 2024 and pay["dates"] == ["2024-04-01", "2024-04-02", "2024-04-05"]
    assert [p["id"] for p in pay["pitchers"]] == ["1_2024", "2_2024"]                      # 선발(9)은 빠진다
    a = pay["pitchers"][0]
    assert a["name"] == "A Reliever" and a["p7d_limit"] == 40.0 and a["il"] is None
    assert a["outings"] == [{"date": "2024-04-01", "pitches": 18, "signals": [], "here": True}, {"date": "2024-04-02", "pitches": 12, "signals": [], "here": True},
                            {"date": "2024-04-05", "pitches": 25, "signals": ["velo"], "here": True}]
    b = pay["pitchers"][1]
    assert b["p7d_limit"] is None and b["il"] == {"date": "2024-04-20", "part": "elbow"}


def test_team_payload_marks_which_outings_were_thrown_for_that_club_but_keeps_all_for_load_metrics():
    o = outings()
    team_map = pd.DataFrame({"pitcher": [1, 1, 1, 2, 2, 9], "game_pk": [1, 2, 3, 1, 3, 1], "team": ["NYY", "NYY", "BOS", "NYY", "NYY", "NYY"]})
    pay = tm.team_payload("NYY", 2024, o, team_map, pd.DataFrame(columns=["pitcher", "season", "game_pk", "velo_alarm", "change_alarm"]),
                          pd.DataFrame(columns=["pitcher", "season", "part", "il_date"]), pd.Series({1: "A", 2: "B", 9: "C"}), pd.Series(dtype=float))
    a = next(p for p in pay["pitchers"] if p["id"] == "1_2024")
    assert [(x["date"], x["here"]) for x in a["outings"]] == [("2024-04-01", True), ("2024-04-02", True), ("2024-04-05", False)]   # 4/5는 BOS 소속 등판
    assert pay["dates"] == ["2024-04-01", "2024-04-02", "2024-04-05"]                       # 팀 경기일은 그 팀 소속 등판이 있던 날
