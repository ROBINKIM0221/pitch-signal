"""고교 모듈 테스트 (SPEC 3.14). 실행: python -m pytest -q"""
import numpy as np
import pandas as pd

from src.common import highschool as hs

RULES = {
    "season": 2026, "schools": 6, "competitions": ["주말리그 전반기", "황금사자기", "기타"],
    "input_ranges": {"game_no": [1, 999], "pitches": [1, 200], "outs": [0, 60], "team_outs_per_game": [1, 30]},
    "window_days": [3, 7],
    "kbsa": {"daily_max": 105, "rest_table": [[45, 0], [60, 1], [75, 2], [90, 3], [105, 4]], "no_three_consecutive_days": True},
    "acwr": {"acute_days": 7, "chronic_days": 21, "flag": 1.5, "min_coverage": 1.0},
    "foreign_rules": {"japan": {"window_days": 7, "max_pitches": 500}, "taiwan": None},
}


def entries(*records):
    """(날짜, 투수 코드, 투구수[, 아웃 수, 경기 번호]) → 입력 표. 학교 코드는 투수 코드 앞 세 글자."""
    rows = []
    for i, (date, pitcher, pitches, *rest) in enumerate(records):
        outs, game_no = (rest[0] if rest else 9), (rest[1] if len(rest) > 1 else 1)
        rows.append({"row": i + 2, "date": pd.Timestamp(date), "competition": "주말리그 전반기", "game_no": game_no,
                     "school": pitcher[:3], "pitcher": pitcher, "pitches": pitches, "outs": outs})
    return pd.DataFrame(rows)


def test_clean_entries_have_no_problems():
    rows = entries(("2026-04-01", "S01-P01", 60), ("2026-04-01", "S01-P02", np.nan), ("2026-04-01", "S02-P01", 45, 27))
    assert hs.problems(rows, RULES).empty                 # 투구수가 빈 줄은 오류가 아니다 (기록에 없는 경우)


def test_problems_name_the_row_and_kind_of_each_format_error():
    rows = entries(("2025-04-01", "S01-P01", 60), ("2026-04-02", "S07-P01", 60), ("2026-04-03", "S01-P1", 60),
                   ("2026-04-04", "S02-P03", 250), ("2026-04-05", "S02-P03", 30, 61), ("2026-04-06", "S02-P03", 30, 9, 0))
    rows.loc[0, "competition"] = "연습경기"
    rows.loc[2, "school"] = "S02"                          # 투수 코드 앞부분과 학교 코드가 다름
    found = hs.problems(rows, RULES)
    assert set(zip(found["row"], found["kind"])) == {
        (2, "날짜"), (2, "대회"), (3, "학교 코드"), (4, "투수 코드"), (5, "투구수"), (6, "아웃 수"), (6, "팀 아웃 수 합"),
        (7, "경기 번호")}                                # 아웃 수 61은 그 경기의 합으로도 걸린다


def test_problems_flag_repeated_entries_and_odd_team_out_totals():
    rows = entries(("2026-04-01", "S01-P01", 60, 15), ("2026-04-01", "S01-P01", 60, 15),      # 같은 날짜·경기·투수
                   ("2026-04-02", "S02-P01", 80, 21), ("2026-04-02", "S02-P02", 40, 12),      # 한 경기 아웃 수 합 33
                   ("2026-04-03", "S03-P01", 5, 0))                                           # 한 경기 아웃 수 합 0
    found = hs.problems(rows, RULES)
    assert set(zip(found["row"], found["kind"])) == {(2, "중복"), (3, "중복"), (4, "팀 아웃 수 합"), (6, "팀 아웃 수 합")}


def test_missing_share_is_reported_per_school():
    rows = entries(("2026-04-01", "S01-P01", 60), ("2026-04-02", "S01-P01", np.nan), ("2026-04-01", "S02-P01", 45))
    assert hs.missing_share(rows).to_dict() == {"S01": 0.5, "S02": 0.0}


def test_recheck_games_draws_the_same_share_of_games_every_time():
    rows = entries(*[(f"2026-04-{d:02d}", f"S01-P{p:02d}", 30) for d in range(1, 21) for p in (1, 2)])
    picked = hs.recheck_games(rows, frac=0.10, seed=7)
    assert len(picked) == 2 and list(picked.columns) == ["date", "game_no", "school"]      # 20경기의 10%
    assert picked.equals(hs.recheck_games(rows, frac=0.10, seed=7))


def test_daily_table_covers_the_schools_season_and_sums_recent_days():
    rows = entries(("2026-04-01", "S01-P01", 30), ("2026-04-02", "S01-P01", 20, 3, 1), ("2026-04-02", "S01-P01", 10, 3, 2),
                   ("2026-04-06", "S01-P02", 50))                    # 2번 투수의 등판이 학교의 수집 기간을 4/6까지 늘림
    one = hs.daily_table(rows, RULES).query("pitcher == 'S01-P01'").set_index("date")
    assert list(one.index) == list(pd.date_range("2026-04-01", "2026-04-06"))
    assert list(one["pitches"]) == [30, 30, 0, 0, 0, 0]              # 같은 날 두 경기는 합산, 등판 없는 날은 0
    assert list(one["sum_3d"]) == [30, 60, 60, 30, 0, 0] and one["sum_7d"].iloc[-1] == 60
    assert not one["acwr_ok"].any()                                  # 수집 기간이 4주가 안 돼 ACWR은 계산 불가


def test_an_outing_without_a_pitch_count_makes_its_windows_unknown_not_zero():
    rows = entries(("2026-04-01", "S01-P01", 30), ("2026-04-03", "S01-P01", np.nan), ("2026-04-08", "S01-P01", 20))
    one = hs.daily_table(rows, RULES).set_index("date")
    assert one.loc["2026-04-03", "unknown"] and np.isnan(one.loc["2026-04-03", "pitches"])
    assert np.isnan(one.loc["2026-04-05", "sum_3d"]) and one.loc["2026-04-06", "sum_3d"] == 0
    assert np.isnan(one.loc["2026-04-08", "sum_7d"])                 # 4/2~4/8 창에 모르는 날이 들어 있음


def loaded_pitcher():
    """규정은 지키지만 마지막 주에 평소의 네 배를 던진 투수."""
    return entries(("2026-04-01", "S01-P01", 30), ("2026-04-08", "S01-P01", 30), ("2026-04-15", "S01-P01", 30),
                   ("2026-04-22", "S01-P01", 30), ("2026-04-29", "S01-P01", 60), ("2026-05-02", "S01-P01", 60))


def test_acwr_is_flagged_once_four_weeks_of_records_exist():
    one = hs.daily_table(loaded_pitcher(), RULES).set_index("date")
    assert not one.loc[:"2026-04-27", "acwr_ok"].any() and one.loc["2026-04-28":, "acwr_ok"].all()
    assert one.loc["2026-04-29", "acwr"] == 2.0 and one.loc["2026-05-02", "acwr"] == 4.0
    assert one.loc["2026-05-02", "acwr_flag"] and not one.loc["2026-04-22", "acwr_flag"]


def test_violations_come_from_the_rule_engine_and_configured_foreign_rules():
    rows = entries(("2026-04-01", "S02-P01", 110), ("2026-04-02", "S02-P01", 20), ("2026-04-03", "S02-P01", 10),
                   ("2026-04-10", "S02-P02", np.nan),
                   *[(f"2026-05-{d:02d}", "S02-P03", 105) for d in (1, 6, 11, 16)],            # 규정대로 4일씩 쉼
                   ("2026-05-21", "S02-P03", 105), ("2026-05-26", "S02-P03", 105))
    found = hs.violations(rows, hs.daily_table(rows, RULES), RULES)
    by_pitcher = found.groupby("pitcher")["rule"].apply(sorted).to_dict()
    assert by_pitcher["S02-P01"] == ["daily_max", "rest", "three_days"]
    assert by_pitcher["S02-P02"] == ["unknown"]
    assert "S02-P03" not in by_pitcher                               # 일본 기준(7일 500구)도 넘지 않음: 7일 안 최대 210구
    assert set(found.columns) == {"school", "pitcher", "date", "rule", "detail"}
    heavy = entries(*[(f"2026-06-{d:02d}", "S03-P01", 105) for d in (1, 2, 3, 4, 5)])
    foreign = hs.violations(heavy, hs.daily_table(heavy, RULES), RULES)
    assert "foreign_japan" in set(foreign["rule"]) and "foreign_taiwan" not in set(foreign["rule"])   # 5일 525구


def test_summary_separates_rule_violations_from_accumulated_load():
    rows = pd.concat([loaded_pitcher(), entries(("2026-04-01", "S01-P02", 110), ("2026-04-02", "S01-P02", 20))])
    daily = hs.daily_table(rows, RULES)
    table = hs.summary(daily, hs.violations(rows, daily, RULES)).set_index("학교")
    s01 = table.loc["S01"]
    assert (s01["투수 수"], s01["규정 위반 건수"], s01["위반 투수 수"]) == (2, 2, 1)
    assert (s01["ACWR 계산 가능 투수 수"], s01["ACWR 기준 초과 투수 수"]) == (2, 1)
    assert s01["위반 없이 누적 부하 표시"] == 1                       # 1번 투수: 규정은 지켰지만 ACWR이 기준을 넘음


def test_read_input_takes_the_filled_rows_of_the_entry_form(tmp_path):
    import shutil

    import openpyxl
    path = tmp_path / "input.xlsx"
    shutil.copy("templates/highschool_input.xlsx", path)
    book = openpyxl.load_workbook(path)
    sheet = book["입력"]
    for r, values in ((2, ["2026-04-01", "주말리그 전반기", 1, "S01", "S01-P01", 60, 15, "기록지 3쪽", "✓"]),
                      (3, ["2026-04-01", "주말리그 전반기", 1, "S01", "S01-P02", None, 12, "투구수 없음", "✓"])):
        for c, value in enumerate(values, start=1):
            sheet.cell(row=r, column=c, value=pd.Timestamp(value).to_pydatetime() if c == 1 else value)
    book.save(path)
    rows = hs.read_input(path)
    assert list(rows.columns) == ["row", "date", "competition", "game_no", "school", "pitcher", "pitches", "outs"]
    assert list(rows["row"]) == [2, 3] and list(rows["pitcher"]) == ["S01-P01", "S01-P02"]     # 빈 줄(4행~)은 버림
    assert rows["date"].iloc[0] == pd.Timestamp("2026-04-01") and rows["pitches"].iloc[0] == 60
    assert np.isnan(rows["pitches"].iloc[1]) and hs.problems(rows, RULES).empty
