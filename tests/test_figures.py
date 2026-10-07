"""최종 그림 테스트 (단계 11.3). 실행: python -m pytest -q tests/test_figures.py"""
import pandas as pd

from src.common import figures as fg
from src.common.config import ROOT


def test_sim_rows_split_the_short_outing_table_into_per_pitch_rates_and_scenarios():
    table = pd.DataFrame({"항목": ["등판 하나 오경보율 (3구)", "등판 하나 오경보율 (16구)", "평소 그대로, 10등판 안 경보", "기용만 짧아짐, 10등판 안 경보"],
                          "분산 하나": [0.021, 0.0065, 0.0716, 0.1058], "가변 표본": [0.01, 0.01, 0.0712, 0.0699]})
    out = fg.sim_rows(table)
    assert list(out["per_outing"]["n"]) == [3, 16]
    assert out["per_outing"]["분산 하나"].tolist() == [0.021, 0.0065]
    assert out["scenarios"]["항목"].tolist() == ["평소 그대로", "기용만 짧아짐"]       # ', 10등판 안 경보'를 떼어 낸 이름
    assert out["scenarios"]["가변 표본"].tolist() == [0.0712, 0.0699]


def replay(window_alarms, pre_alarm=False):
    """시작 구간 2등판 + 감시 7등판짜리 리플레이. 마지막 5등판이 관찰 창."""
    base = [{"date": f"2025-04-0{i}", "game_pk": i, "n_fb": 20, "phase": "baseline", "velo": 93.0} for i in (1, 2)]
    mon = []
    for i in range(3, 10):
        in_window = i >= 5
        alarm = (pre_alarm and i == 3) or (in_window and window_alarms[i - 5])
        mon.append({"date": f"2025-05-{i:02d}", "game_pk": i, "n_fb": 20, "phase": "monitor", "velo": 92.0,
                    "exp": {"velo": 93.0}, "sd": {"velo": 0.9}, "velo_index": 1.2 if alarm else 0.3, "velo_alarm": alarm})
    return {"name": "A", "role": "SP", "part": "elbow", "season": 2025, "il_date": "2025-05-10", "baseline_end": "2025-04-02",
            "window": [5, 6, 7, 8, 9], "detected": any(window_alarms), "outings": base + mon}


def test_replay_story_counts_lead_from_the_first_window_alarm_and_alarms_before_the_window():
    s = fg.replay_story(replay([False, True, False, True, False], pre_alarm=True))
    assert s["lead"] == 4 and s["pre_window_alarms"] == 1
    assert s["in_window"].tolist() == [False] * 2 + [True] * 5 and len(s["dates"]) == 7       # 감시 등판만, 창 표시 포함
    assert s["detected"]


def test_replay_story_has_no_lead_when_nothing_rang_in_the_window():
    s = fg.replay_story(replay([False] * 5))
    assert s["lead"] is None and not s["detected"] and s["pre_window_alarms"] == 0


def test_kbo_timeline_counts_days_from_removal_to_decision():
    rows = fg.kbo_timeline([{"pitcher": "A", "team": "LG", "removed": "2026-04-22", "decided": "2026-06-02", "kind": "완전 교체"}])
    assert rows.loc[0, "days"] == 41


def test_draw_all_writes_every_figure_it_has_real_data_for(tmp_path):
    written = fg.draw_all(tmp_path)
    names = sorted(p.name for p in tmp_path.glob("*.png"))
    assert names == ["01_system.png", "02_short_outings.png", "03_opcurve_val.png", "04_case_detected.png",
                     "05_case_missed.png", "06_highschool.png", "06b_tournament.png", "07_kbo_timeline.png"]   # ⑥ 고교는 2025 경기도 시즌·전국체전 실제 기록
    assert set(written) == set(names)
    captions = (tmp_path / "captions.md").read_text(encoding="utf-8")
    for name in names:
        assert name in captions
    results = pd.read_csv(ROOT / "reports" / "tables" / "val_results.csv")
    velo = results[(results["method"] == "구속 하락 신호") & (results["group"] == "all")].iloc[0]
    assert f"{velo['detection']:.1f}%" in captions and f"{velo['control_window']:.1f}%" in captions    # 캡션 숫자는 결과 파일에서 온다
    assert "가상" not in captions.replace("가상 데이터는 쓰지 않", "")
    assert "전국체전" in captions and "등번호" in captions and "경기 권역" in captions        # ⑥ 캡션은 시즌(경기 권역)·대회 자료(학교 실명·등번호)로 쓴다
