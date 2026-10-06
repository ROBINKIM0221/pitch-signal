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
