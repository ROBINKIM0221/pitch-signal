"""팀 불펜 현황판(화면 4) 자료: 투수가 어느 팀 소속으로 던졌는지(원데이터의 홈·원정과 초·말)와 팀-시즌별 불펜 투수 등판 목록.

날짜별 부하 상태(3일 등판, 7일 투구, ACWR, 연투)는 화면이 등판 목록으로 다시 계산한다 (dashboard-web/src/lib/load.js,
정의는 src/common/load.py와 같다). 여기서는 계산에 필요한 재료만 내보낸다.
"""
from __future__ import annotations

import pandas as pd

SIGNALS = ["velo", "change"]


def team_of_outing(raw: pd.DataFrame) -> pd.DataFrame:
    """투구 원데이터(pitcher, game_pk, home_team, away_team, inning_topbot) → 등판(pitcher, game_pk)마다 소속 팀.
    초(Top)에 던진 투수는 홈 팀, 말(Bot)에 던진 투수는 원정 팀이다."""
    first = raw.drop_duplicates(["pitcher", "game_pk"])
    team = first["home_team"].where(first["inning_topbot"] == "Top", first["away_team"])
    return pd.DataFrame({"pitcher": first["pitcher"].to_numpy(), "game_pk": first["game_pk"].to_numpy(), "team": team.to_numpy()})


def _date(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def team_payload(team: str, season: int, outings: pd.DataFrame, team_map: pd.DataFrame, alarms: pd.DataFrame, labels: pd.DataFrame,
                 names: pd.Series, limits: pd.Series) -> dict:
    """한 팀-시즌의 불펜(role == RP) 투수마다 그 시즌 등판 전부(날짜, 투구 수, 품질 경보, 이 팀 소속 여부), 7일 투구 한계값, 첫 팔 부상 IL.
    outings: outings.parquet의 그 시즌 줄. team_map: team_of_outing 결과. alarms: monitor 표의 (pitcher, season, game_pk, velo_alarm, change_alarm).
    limits: (pitcher, season) → p7d_limit."""
    season_outings = outings[outings["season"] == season].merge(team_map, on=["pitcher", "game_pk"], how="left")
    here = season_outings[season_outings["team"] == team]
    relievers = sorted(here.loc[here["role"] == "RP", "pitcher"].unique())
    alarm_key = alarms[alarms["season"] == season].set_index(["pitcher", "game_pk"])
    arm_il = labels[(labels["season"] == season) & labels["part"].isin(["elbow", "shoulder"])].sort_values("il_date").drop_duplicates("pitcher").set_index("pitcher")
    pitchers = []
    for pitcher in relievers:
        mine = season_outings[season_outings["pitcher"] == pitcher].sort_values(["game_date", "game_pk"])
        rows = []
        for o in mine.itertuples():
            signals = []
            if (pitcher, o.game_pk) in alarm_key.index:
                a = alarm_key.loc[(pitcher, o.game_pk)]
                signals = [s for s in SIGNALS if bool(a[f"{s}_alarm"])]
            rows.append({"date": _date(o.game_date), "pitches": int(o.n_all), "signals": signals, "here": o.team == team})
        limit = limits.get((pitcher, season), float("nan"))
        il = arm_il.loc[pitcher] if pitcher in arm_il.index else None
        pitchers.append({"id": f"{pitcher}_{season}", "name": names.get(pitcher, str(pitcher)), "outings": rows,
                         "p7d_limit": None if pd.isna(limit) else round(float(limit), 1),
                         "il": None if il is None else {"date": _date(il["il_date"]), "part": il["part"]}})
    dates = sorted(here["game_date"].map(_date).unique())
    return {"team": team, "season": int(season), "dates": dates, "pitchers": pitchers}
