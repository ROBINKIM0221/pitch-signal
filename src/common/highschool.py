"""고교 투구수 모듈 (SPEC 3.14). 입력 검사와, 규정 위반·누적 부하 계산.

규정 판정과 ACWR은 src/core/kbsa_rules.py를 그대로 쓴다. 학교는 S01~, 투수는 S01-P03 같은 가명 코드만 다룬다.
입력 표의 열: row(엑셀 줄 번호), date, competition, game_no, school, pitcher, pitches, outs
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from src.core import kbsa_rules as kr

SHEET = "입력"
COLUMNS = {"날짜": "date", "대회": "competition", "경기 번호": "game_no", "학교 코드": "school", "투수 코드": "pitcher",
           "투구수": "pitches", "아웃 수 (이닝×3)": "outs"}
PITCHER_CODE = re.compile(r"^S\d{2}-P\d{2}$")
GAME = ["date", "game_no", "school"]
KBSA_RULES = ["daily_max", "rest", "three_days"]        # kbsa_rules.check_violations가 내는 위반 종류 (unknown은 판정 불가)


def read_input(path) -> pd.DataFrame:
    """입력 양식(templates/highschool_input.xlsx와 같은 형식)을 읽는다. 투수 코드가 빈 줄은 버린다."""
    sheet = pd.read_excel(path, sheet_name=SHEET, usecols=list(COLUMNS)).rename(columns=COLUMNS)
    sheet.insert(0, "row", sheet.index + 2)             # 엑셀에서는 머리글이 1행
    rows = sheet[sheet["pitcher"].notna()].copy()
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    for column in ("game_no", "pitches", "outs"):
        rows[column] = pd.to_numeric(rows[column], errors="coerce")
    return rows.reset_index(drop=True)


def _outside(values: pd.Series, limits: list, blank_ok: bool = False) -> pd.Series:
    """정수가 아니거나 범위 밖인 값. blank_ok면 빈칸은 봐준다."""
    whole = values.notna() & (values % 1 == 0) & values.between(*limits)
    return ~(whole | (values.isna() & blank_ok))


def problems(rows: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """입력 오류 목록: row, school, kind, detail. 형식 오류, 같은 날짜·경기·투수 중복, 한 경기 팀 아웃 수 합 이상."""
    ranges = rules["input_ranges"]
    schools = [f"S{i:02d}" for i in range(1, rules["schools"] + 1)]
    code_ok = rows["pitcher"].astype(str).str.match(PITCHER_CODE) & (rows["pitcher"].astype(str).str[:3] == rows["school"])
    checks = {
        "날짜": (rows["date"].dt.year != rules["season"], f"{rules['season']}년 날짜가 아님"),
        "대회": (~rows["competition"].isin(rules["competitions"]), "대회 목록에 없음"),
        "경기 번호": (_outside(rows["game_no"], ranges["game_no"]), "범위 밖이거나 정수가 아님"),
        "학교 코드": (~rows["school"].isin(schools), "학교 코드 목록에 없음"),
        "투수 코드": (~code_ok, "형식이 '학교 코드-P두자리'가 아니거나 학교 코드와 다름"),
        "투구수": (_outside(rows["pitches"], ranges["pitches"], blank_ok=True), "범위 밖이거나 정수가 아님"),
        "아웃 수": (_outside(rows["outs"], ranges["outs"]), "범위 밖이거나 정수가 아님"),
        "중복": (rows.duplicated(["date", "game_no", "pitcher"], keep=False), "같은 날짜·경기 번호·투수가 두 번 입력됨"),
    }
    found = [rows.loc[bad, ["row", "school"]].assign(kind=kind, detail=detail) for kind, (bad, detail) in checks.items()]
    low, high = ranges["team_outs_per_game"]
    games = rows.groupby(GAME, as_index=False).agg(row=("row", "min"), outs=("outs", "sum"))
    odd = games[~games["outs"].between(low, high)]
    found.append(odd[["row", "school"]].assign(kind="팀 아웃 수 합", detail="한 경기 아웃 수 합 " + odd["outs"].astype(int).astype(str)))
    return pd.concat(found, ignore_index=True).sort_values(["row", "kind"], ignore_index=True)


def missing_share(rows: pd.DataFrame) -> pd.Series:
    """학교별 투구수가 비어 있는 줄의 비율."""
    return rows["pitches"].isna().groupby(rows["school"]).mean()


def recheck_games(rows: pd.DataFrame, frac: float, seed: int) -> pd.DataFrame:
    """원래 기록과 다시 대조할 경기(date, game_no, school)를 전체의 frac만큼 무작위로 고른다. 적어도 한 경기."""
    games = rows[GAME].drop_duplicates().sort_values(GAME, ignore_index=True)
    count = max(1, int(np.ceil(len(games) * frac)))
    return games.sample(count, random_state=seed).sort_values(GAME, ignore_index=True)


def _recent_sum(daily: pd.Series, days: int) -> pd.Series:
    """최근 days일 투구 수 합. 투구 수를 모르는 날이 창에 들어 있으면 NaN(계산 불가)."""
    total = daily.fillna(0).rolling(days, min_periods=1).sum()
    return total.where(daily.isna().rolling(days, min_periods=1).sum() == 0)


def daily_table(rows: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """투수마다 하루 한 줄: 투구 수, 최근 며칠 누적, ACWR.

    수집 기간은 그 학교의 첫 경기일부터 마지막 경기일까지다. 같은 날 두 경기는 합산하고 등판 없는 날은 0,
    등판했지만 투구 수를 모르는 날은 NaN(unknown)이다. ACWR은 직전 3주가 모두 수집 기간일 때만 계산한다(acwr_ok).
    """
    a = rules["acwr"]
    parts = []
    for school, team in rows.groupby("school"):
        days = pd.date_range(team["date"].min(), team["date"].max(), freq="D")
        covered = pd.Series(True, index=days)
        for pitcher, log in team.groupby("pitcher"):
            daily = kr.daily_series(log[["date", "pitches"]], days[0], days[-1])
            load = kr.acwr(daily, a["acute_days"], a["chronic_days"], coverage=covered, min_coverage=a["min_coverage"])
            part = pd.DataFrame({"school": school, "pitcher": pitcher, "date": days, "pitches": daily.to_numpy(),
                                 "unknown": daily.isna().to_numpy()})
            for window in rules["window_days"]:
                part[f"sum_{window}d"] = _recent_sum(daily, window).to_numpy()
            part["acwr"], part["acwr_ok"] = load["acwr"].to_numpy(), load["eligible"].to_numpy()
            part["acwr_flag"] = part["acwr_ok"] & (part["acwr"] > a["flag"])
            parts.append(part)
    return pd.concat(parts, ignore_index=True)


def violations(rows: pd.DataFrame, daily: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """규정 위반 목록: school, pitcher, date, rule, detail.

    rule은 KBSA 규정(daily_max, rest, three_days), 판정 불가(unknown), 해외 규정(foreign_<이름>, 설정에 값이 있는 것만).
    """
    k = rules["kbsa"]
    found = []
    for (school, pitcher), log in rows.groupby(["school", "pitcher"]):
        hits = kr.check_violations(log[["date", "pitches"]], k["daily_max"], k["rest_table"], k["no_three_consecutive_days"])
        found.append(hits.assign(school=school, pitcher=pitcher))
    for name, rule in rules["foreign_rules"].items():
        if not rule:
            continue
        for (school, pitcher), days in daily.groupby(["school", "pitcher"]):
            hits = kr.window_limit_violations(days.set_index("date")["pitches"], rule["window_days"], rule["max_pitches"])
            found.append(pd.DataFrame({
                "date": hits["date"], "rule": f"foreign_{name}", "school": school, "pitcher": pitcher,
                "detail": [f"{rule['window_days']}일 {int(total)}구 > {rule['max_pitches']}구" for total in hits["window_sum"]]}))
    return pd.concat(found, ignore_index=True)[["school", "pitcher", "date", "rule", "detail"]]


def summary(daily: pd.DataFrame, violated: pd.DataFrame) -> pd.DataFrame:
    """학교별 요약. 규정 위반(KBSA)과 누적 부하(ACWR 기준 초과)를 따로 센다."""
    kbsa = violated[violated["rule"].isin(KBSA_RULES)]
    per = daily.groupby(["school", "pitcher"]).agg(ok=("acwr_ok", "any"), flag=("acwr_flag", "any"),
                                                  unknown=("unknown", "sum")).reset_index()
    per["violations"] = per["pitcher"].map(kbsa.groupby("pitcher").size()).fillna(0).astype(int)
    grouped = per.groupby("school")
    table = pd.DataFrame({
        "투수 수": grouped.size(),
        "규정 위반 건수": grouped["violations"].sum(),
        "위반 투수 수": grouped["violations"].apply(lambda v: int((v > 0).sum())),
        "투구수 모르는 등판일 수": grouped["unknown"].sum(),
        "ACWR 계산 가능 투수 수": grouped["ok"].sum(),
        "ACWR 기준 초과 투수 수": grouped["flag"].sum(),
        "위반 없이 누적 부하 표시": per[(per["violations"] == 0) & per["flag"]].groupby("school").size(),
    }).fillna(0).astype(int)
    table["ACWR 기준 초과 비율"] = (table["ACWR 기준 초과 투수 수"] / table["ACWR 계산 가능 투수 수"]).round(3)
    return table.rename_axis("학교").reset_index()
