"""영입 전 점검(화면 5) 요약 테스트. 실행: python -m pytest -q tests/test_scout.py"""
import numpy as np
import pandas as pd

from src.common import scout


def season_rows(pitcher, season, velos, phase_from, alarms=(), league="MLB"):
    rows = []
    for i, v in enumerate(velos):
        rows.append({"pitcher": pitcher, "season": season, "league": league, "role": "SP", "game_pk": i + 1, "game_date": pd.Timestamp(f"{season}-04-01") + pd.Timedelta(days=5 * i),
                     "n_fb": 40, "velo": v, "phase": "baseline" if i < phase_from else "monitor",
                     "velo_alarm": i in alarms, "change_alarm": False, "velo_index": 1.2 if i in alarms else 0.1, "change_index": 0.2})
    return pd.DataFrame(rows)


def test_season_summary_reports_velocity_at_start_and_end_and_alarm_counts():
    t = season_rows(1, 2024, [94, 94, 94, 95, 94, 93, 92, 92, 91, 91], phase_from=3, alarms=(7, 8))
    s = scout.season_summary(t)
    assert s["outings"] == 10 and s["monitored"] == 7
    assert abs(s["velo_start"] - 94.0) < 1e-9                        # 시작 구간 평균
    assert abs(s["velo_last5"] - np.mean([93, 92, 92, 91, 91])) < 1e-9
    assert abs(s["velo_change"] - (np.mean([93, 92, 92, 91, 91]) - 94.0)) < 1e-9
    assert s["alarms_velo"] == 2 and s["alarms_change"] == 0 and s["first_alarm"] == "2024-05-06"


def test_arm_il_in_season_picks_the_first_elbow_or_shoulder_il_of_that_pitcher_season():
    labels = pd.DataFrame({"pitcher": [1, 1, 2], "season": [2024, 2024, 2024], "part": ["shoulder", "elbow", "elbow"],
                           "il_date": pd.to_datetime(["2024-08-01", "2024-06-01", "2024-07-01"])})
    assert scout.arm_il(labels, 1, 2024) == {"date": "2024-06-01", "part": "elbow"}
    assert scout.arm_il(labels, 3, 2024) is None


def test_timeline_concatenates_seasons_in_order_with_league_and_alarm_flags():
    a = season_rows(1, 2023, [90, 91], phase_from=1, league="AAA")
    b = season_rows(1, 2024, [92, 93], phase_from=1, alarms=(1,))
    tl = scout.timeline(pd.concat([a, b]))
    assert [x["season"] for x in tl] == [2023, 2023, 2024, 2024]
    assert tl[0]["league"] == "AAA" and tl[-1]["alarm"] is True and tl[-1]["velo"] == 93


RULES = {"il_days": [7, 10, 15, 60], "max_retro_days": 10,
         "arm_keywords": ["elbow", "ucl", "forearm", "flexor", "shoulder", "rotator cuff", "labrum"], "shoulder_keywords": ["shoulder", "rotator cuff", "labrum"],
         "exclude_keywords": ["oblique", "hamstring", "ankle"]}


def test_il_placements_keeps_every_new_il_of_the_listed_pitchers_and_names_the_part_when_a_reason_exists():
    tx = pd.DataFrame([
        {"id": 1, "person_id": 10, "person_name": "A", "date": "2025-06-09", "effective_date": "2025-06-09", "description": "Lehigh Valley IronPigs placed RHP A on the 7-day injured list retroactive to June 9, 2025. Right shoulder discomfort."},
        {"id": 2, "person_id": 10, "person_name": "A", "date": "2025-07-20", "effective_date": "2025-07-18", "description": "Lehigh Valley IronPigs placed RHP A on the 7-day injured list."},
        {"id": 3, "person_id": 11, "person_name": "B", "date": "2024-05-02", "effective_date": "2024-05-02", "description": "Iowa Cubs placed LHP B on the 7-day injured list. Left oblique strain."},
        {"id": 4, "person_id": 11, "person_name": "B", "date": "2024-05-20", "effective_date": "2024-05-20", "description": "Iowa Cubs activated LHP B from the 7-day injured list."},
        {"id": 5, "person_id": 12, "person_name": "C", "date": "2024-05-02", "effective_date": "2024-05-02", "description": "Iowa Cubs placed RHP C on the 7-day injured list. Right elbow inflammation."},
        {"id": 6, "person_id": 10, "person_name": "A", "date": "2025-06-09", "effective_date": "2025-06-09", "description": "Lehigh Valley IronPigs placed RHP A on the 7-day injured list retroactive to June 9, 2025. Right shoulder discomfort."},
    ])
    out = scout.il_placements(tx, [10, 11], RULES)
    assert len(out) == 3                                             # 복귀(activated)는 빼고, 목록에 없는 C는 빼고, 같은 기록 반복은 하나만
    assert list(out.columns) == ["pitcher", "season", "il_date", "days", "part", "reason"]
    a = out[out["pitcher"] == 10].sort_values("il_date")
    assert a["part"].tolist() == ["shoulder", "unknown"] and a["reason"].tolist()[1] is None
    assert a["il_date"].tolist() == [pd.Timestamp("2025-06-09"), pd.Timestamp("2025-07-18")]       # 소급일 → effective_date 순
    assert out.loc[out["pitcher"] == 11, "part"].tolist() == ["other"] and out["days"].tolist() == [7, 7, 7]


def test_season_il_prefers_an_arm_injury_over_an_earlier_unknown_one():
    placements = pd.DataFrame({"pitcher": [10, 10, 10], "season": [2025, 2025, 2024], "il_date": pd.to_datetime(["2025-05-01", "2025-06-09", "2024-08-01"]),
                               "days": [7, 7, 7], "part": ["unknown", "shoulder", "unknown"], "reason": [None, "Right shoulder discomfort.", None]})
    assert scout.season_il(placements, 10, 2025) == {"date": "2025-06-09", "part": "shoulder", "reason": "Right shoulder discomfort.", "count": 2}
    assert scout.season_il(placements, 10, 2024) == {"date": "2024-08-01", "part": "unknown", "reason": None, "count": 1}
    assert scout.season_il(placements, 10, 2023) is None
