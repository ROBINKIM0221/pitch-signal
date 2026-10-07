"""전국체전 기록 변환: KBSA 경기 기록(실명) → 가명 코드 입력표(고교 모듈 형식) → 등판별 휴식일 주석.

실명이 든 표(team, name, number)는 이 모듈 안에서만 다루고, 밖으로는 name_map()이 만든 대응표(저장소 밖에 저장)와
가명 코드만 나간다. 규칙 계산은 src/core/kbsa_rules.py와 src/common/highschool.py를 그대로 쓴다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.common.config import ROOT, _merge, load_config
from src.core import kbsa_rules as kr

GAME_KEY = ["game_idx", "team", "name", "number"]


def tournament_config(root: Path = ROOT) -> tuple[dict, dict]:
    """(config_kbsa.yaml의 대회 설정, 고교 규칙) — 규칙은 config.yaml highschool 블록에 overrides를 덮어쓴 것."""
    t = yaml.safe_load((Path(root) / "config_kbsa.yaml").read_text(encoding="utf-8"))["tournament"]
    return t, _merge(load_config(root)["highschool"], t["overrides"])


def mark_missing_detail(table: pd.DataFrame) -> pd.DataFrame:
    """상세 기록이 안 올라온 경기(모든 투수의 아웃·투구수가 0)는 detail=False, 투구 수는 모름(NA)으로 바꾼다."""
    t = table.copy()
    totals = t.groupby("game_idx").agg(outs=("outs", "sum"), pitches=("pitches", lambda s: s.fillna(0).sum()))
    missing = totals.index[(totals["outs"] == 0) & (totals["pitches"] == 0)]
    t["detail"] = ~t["game_idx"].isin(missing)
    t["pitches"] = t["pitches"].astype("Int64").where(t["detail"], pd.NA)
    return t


def combine_stints(table: pd.DataFrame) -> pd.DataFrame:
    """한 경기에 두 번 등판한 투수는 한 줄로 합친다 (아웃·타자·투구수 합, 등판 구분은 첫 번째, 결과는 승·패가 있으면 그것)."""
    t = table.copy()
    if "detail" not in t:
        t["detail"] = True
    t["_order"] = range(len(t))
    agg = {"date": "first", "opponent": "first", "role": "first", "innings": "first", "detail": "first", "_order": "min",
           "outs": "sum", "batters": lambda s: s.sum(min_count=1), "pitches": lambda s: s.sum(min_count=1),
           "result": lambda s: next((r for r in s if r in ("승", "패")), s.iloc[0]), "stints": "size"}
    out = (t.assign(stints=1).groupby(GAME_KEY, as_index=False, sort=False).agg(agg)
            .sort_values("_order").drop(columns="_order").reset_index(drop=True))
    out["pitches"] = out["pitches"].astype("Int64")
    out["batters"] = out["batters"].astype("Int64")
    return out


def name_map(table: pd.DataFrame, seed: int) -> pd.DataFrame:
    """실명 → 가명 대응표: 학교는 S01~ (씨앗으로 섞은 순서), 투수는 학교 안에서 Sxx-P01~ (역시 섞은 순서).
    같은 입력과 씨앗이면 늘 같은 코드가 나온다. 이 표는 저장소 밖(비공개 폴더)에만 저장한다."""
    rng = np.random.default_rng(seed)
    teams = sorted(table["team"].unique())
    school_of = dict(zip(rng.permutation(teams), [f"S{i:02d}" for i in range(1, len(teams) + 1)]))
    rows = []
    for team in teams:
        people = sorted(table.loc[table["team"] == team, ["name", "number"]].drop_duplicates().itertuples(index=False))
        order = rng.permutation(len(people))
        for rank, idx in enumerate(order, start=1):
            name, number = people[idx]
            rows.append({"team": team, "name": name, "number": int(number), "school": school_of[team], "pitcher": f"{school_of[team]}-P{rank:02d}"})
    return pd.DataFrame(rows).sort_values(["school", "pitcher"], ignore_index=True)


def input_rows(table: pd.DataFrame, names: pd.DataFrame, competition: str, rounds: dict[str, int]) -> pd.DataFrame:
    """고교 모듈 입력표 형식(row, date, competition, game_no, school, pitcher, pitches, outs)에 대회용 열을 더한 가명 표.
    game_no는 경기 순서(1~), round는 rounds(라운드 이름 → 경기 수)를 순서대로 배정한 것."""
    key = names.set_index(["team", "name", "number"])
    codes = key.loc[list(zip(table["team"], table["name"], table["number"]))].reset_index(drop=True)
    school_code = names.drop_duplicates("team").set_index("team")["school"]
    games = sorted(table["game_idx"].unique(), key=lambda g: (table.loc[table["game_idx"] == g, "date"].iloc[0], g))
    round_of, labels = {}, [name for name, count in rounds.items() for _ in range(count)]
    if len(labels) != len(games):
        raise ValueError(f"라운드 경기 수 합 {len(labels)} ≠ 경기 수 {len(games)}")
    for g, label in zip(games, labels):
        round_of[g] = label
    out = pd.DataFrame({
        "row": range(2, len(table) + 2), "date": table["date"].to_numpy(), "competition": competition,
        "game_no": table["game_idx"].map({g: i + 1 for i, g in enumerate(games)}).to_numpy(),
        "school": codes["school"].to_numpy(), "pitcher": codes["pitcher"].to_numpy(),
        "pitches": table["pitches"].astype("Float64").astype(float).to_numpy(), "outs": table["outs"].astype(int).to_numpy(),
        "opponent": table["opponent"].map(school_code).to_numpy(), "role": table["role"].to_numpy(), "result": table["result"].to_numpy(),
        "round": table["game_idx"].map(round_of).to_numpy(), "game_idx": table["game_idx"].to_numpy(), "detail": table["detail"].to_numpy(),
        "stints": table["stints"].to_numpy() if "stints" in table else 1})
    return out.sort_values(["game_no", "school", "row"], ignore_index=True)


def annotate_outings(rows: pd.DataFrame, kbsa: dict) -> pd.DataFrame:
    """등판마다 직전 등판과의 간격(gap_days: 사이에 쉰 날 수), 직전 투구 수가 요구하는 휴식일(required_rest), 지켰는지(rest_ok),
    의무 휴식일(1일 이상)을 꼭 채우고 첫 가능일에 등판했는지(min_rest_exact; 휴식 0일 뒤 연투는 gap_days=0으로 따로 센다),
    대회 누적 투구 수(cum_pitches; 모르는 경기 뒤는 NaN)."""
    rest_table = [tuple(r) for r in kbsa["rest_table"]]
    out = rows.sort_values(["pitcher", "date", "game_no"]).copy()
    gap, req, ok, exact, cum = [], [], [], [], []
    for _, log in out.groupby("pitcher", sort=False):
        prev_date, prev_pitches, total = None, None, 0.0
        for r in log.itertuples():
            if prev_date is None:
                gap.append(np.nan); req.append(np.nan); ok.append(None); exact.append(None)
            else:
                g = (r.date - prev_date).days - 1
                need = kr.required_rest(int(prev_pitches), rest_table) if pd.notna(prev_pitches) else np.nan
                gap.append(g); req.append(need)
                ok.append(None if pd.isna(need) else bool(g >= need))
                exact.append(None if pd.isna(need) else bool(need >= 1 and g == need))
            total = total + r.pitches if pd.notna(r.pitches) and not np.isnan(total) else np.nan
            cum.append(total)
            prev_date, prev_pitches = r.date, r.pitches
    out["gap_days"], out["required_rest"], out["cum_pitches"] = gap, req, cum
    out["rest_ok"] = pd.Series(ok, index=out.index, dtype=object)
    out["min_rest_exact"] = pd.Series(exact, index=out.index, dtype=object)
    return out.sort_values(["game_no", "school", "row"], ignore_index=True)


def _clean(value):
    """JSON으로 내보낼 값: 결측은 None, numpy 수는 파이썬 수."""
    if value is None or (isinstance(value, float) and np.isnan(value)) or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if np.isnan(value) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _rec(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
    return [{c: _clean(v) for c, v in zip(columns, row)} for row in frame[columns].itertuples(index=False)]


GAME_COLUMNS = ["date", "game_no", "round", "opponent", "role", "result", "outs", "pitches", "detail", "gap_days", "required_rest", "rest_ok", "min_rest_exact", "cum_pitches"]
DAY_COLUMNS = ["date", "pitches", "sum_3d", "sum_7d"]


def payload(outings: pd.DataFrame, daily: pd.DataFrame, violated: pd.DataFrame, rules: dict, info: dict) -> dict:
    """대시보드 highschool.json (대회 모드). 가명 코드만 들어간다."""
    from src.common import highschool as hs
    kbsa_rules = set(hs.KBSA_RULES)
    games = (outings.sort_values("game_no").groupby("game_no").agg(date=("date", "first"), round=("round", "first"), detail=("detail", "first"),
                                                                    teams=("school", lambda s: sorted(s.unique()))).reset_index())
    game_list = [{"no": int(g.game_no), "date": _clean(g.date), "round": g.round, "teams": list(g.teams), "detail": bool(g.detail)} for g in games.itertuples()]
    schools = []
    for school, mine in outings.groupby("school"):
        pitchers = []
        for code, g in mine.groupby("pitcher"):
            g = g.sort_values(["date", "game_no"])
            v = violated[violated["pitcher"] == code]
            real = v[v["rule"].isin(kbsa_rules)]
            status = "위반" if len(real) else ("판정 불가" if (v["rule"] == "unknown").any() else "준수")
            known = g["pitches"].notna().all()
            d = daily[(daily["pitcher"] == code) & ((daily["pitches"].fillna(0) != 0) | daily["unknown"])]
            pitchers.append({"code": code, "rule_status": status, "outings": int(len(g)),
                             "pitches_total": int(g["pitches"].sum()) if known else None, "max_pitches": _clean(g["pitches"].max()),
                             "back_to_back": int((g["gap_days"] == 0).sum()), "min_rest_exact": int((g["min_rest_exact"] == True).sum()),
                             "violations": _rec(v, ["date", "rule", "detail"]), "games": _rec(g, GAME_COLUMNS),
                             "days": [{**r, "acwr": None, "flag": False} for r in _rec(d, DAY_COLUMNS)]})
        schools.append({"code": school, "games": int(mine["game_no"].nunique()), "pitchers": pitchers})
    second = outings[outings["gap_days"].notna()]
    totals = {"schools": int(outings["school"].nunique()), "pitchers": int(outings["pitcher"].nunique()), "outings": int(len(outings)),
              "unknown_outings": int(outings["pitches"].isna().sum()),
              "violations": int(violated["rule"].isin(kbsa_rules).sum()), "rest_violations": int((second["rest_ok"] == False).sum()),
              "back_to_back": int((second["gap_days"] == 0).sum()), "min_rest_exact": int((second["min_rest_exact"] == True).sum()),
              "games_100plus": int((outings["pitches"] >= 100).sum()), "games_91plus": int((outings["pitches"] >= 91).sum()),
              "pitchers_3plus_games": int((outings.groupby("pitcher").size() >= 3).sum()),
              "max_total": _clean(outings.groupby("pitcher")["pitches"].sum(min_count=1).max())}
    no_detail = sorted(int(g) for g in outings.loc[~outings["detail"], "game_no"].unique())
    return {"synthetic": False, "mode": "tournament", "season": rules["season"], "acwr_flag": rules["acwr"]["flag"], "kbsa": rules["kbsa"],
            "foreign_rules": {k: v for k, v in rules["foreign_rules"].items() if v},
            "tournament": {"name": info["name"], "short": info["short"], "season": info["season"], "dates": info["dates"], "source": info["source"],
                           "games": int(outings["game_no"].nunique()), "no_detail_games": no_detail},
            "games": game_list, "schools": schools, "totals": totals,
            "summary": [{k: _clean(v) for k, v in r.items()} for r in hs.summary(daily, violated).to_dict("records")]}
