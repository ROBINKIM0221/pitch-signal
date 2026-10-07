"""KBSA 경기 기록 → 고교 모듈 입력표 → 등판별 휴식일 주석 → 대시보드 payload (시즌 모드·대회 모드).

선수 실명이 든 표(team, name, number)는 이 모듈 안에서만 다루고, 밖으로는 name_map()이 만든 대응표(저장소 밖에 저장)와
학교 실명·등번호 표기(#17)만 나간다. 규칙 계산은 src/core/kbsa_rules.py와 src/common/highschool.py를 그대로 쓴다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.common import highschool as hs
from src.common.config import ROOT, _merge, load_config
from src.core import kbsa_rules as kr

GAME_KEY = ["game_idx", "team", "name", "number"]
GAME_COLUMNS = ["date", "game_no", "competition", "round", "opponent", "role", "result", "outs", "pitches", "detail", "gap_days", "required_rest", "rest_ok", "min_rest_exact", "cum_pitches"]
DAY_COLUMNS = ["date", "pitches", "sum_3d", "sum_7d", "acwr", "acwr_flag"]


def datasets_config(root: Path = ROOT) -> tuple[dict, dict[str, tuple[dict, dict]]]:
    """config_kbsa.yaml → (공통 설정, {데이터셋 키: (데이터셋 설정, 고교 규칙)}). 규칙은 config.yaml highschool 블록에 overrides를 덮어쓴 것
    (schools 수는 변환 때 팀 수로 채운다)."""
    cfg = yaml.safe_load((Path(root) / "config_kbsa.yaml").read_text(encoding="utf-8"))
    base = load_config(root)["highschool"]
    return cfg, {key: (d, _merge(base, d["overrides"])) for key, d in cfg["datasets"].items()}


def mark_missing_detail(table: pd.DataFrame) -> pd.DataFrame:
    """상세 기록이 안 올라온 경기(모든 투수의 아웃·투구수가 0)는 detail=False, 투구 수는 모름(NA)으로 바꾼다.
    아웃이나 타자가 있는데 투구수가 0인 줄(기록 누락)도 투구 수 모름으로 둔다."""
    t = table.copy()
    totals = t.groupby("game_idx").agg(outs=("outs", "sum"), pitches=("pitches", lambda s: s.fillna(0).sum()))
    missing = totals.index[(totals["outs"] == 0) & (totals["pitches"] == 0)]
    t["detail"] = ~t["game_idx"].isin(missing)
    faced = (t["outs"].fillna(0) > 0) | (t["batters"].fillna(0) > 0)
    t["pitches"] = t["pitches"].astype("Int64").where(t["detail"] & ~((t["pitches"].fillna(0) == 0) & faced), pd.NA)
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


def name_map(table: pd.DataFrame) -> pd.DataFrame:
    """실명 → 코드·표기 대응표: 학교는 이름순 S01~(코드는 계산용, 화면에는 학교 실명), 투수는 학교 안에서 Sxx-P01~(등번호·이름순)이고
    표기는 등번호 '#17'(같은 번호가 둘이면 '#17b'). 같은 입력이면 늘 같은 결과. 이 표는 저장소 밖(비공개 폴더)에만 저장한다."""
    teams = sorted(table["team"].unique())
    school_of = {team: f"S{i:02d}" for i, team in enumerate(teams, start=1)}
    rows = []
    for team in teams:
        people = (table.loc[table["team"] == team, ["name", "number"]].drop_duplicates()
                       .assign(number=lambda d: d["number"].astype(int)).sort_values(["number", "name"]).reset_index(drop=True))
        seen: dict[int, int] = {}
        for rank, (name, number) in enumerate(people.itertuples(index=False), start=1):
            suffix = "" if number not in seen else "bcdefgh"[seen[number] - 1]
            seen[number] = seen.get(number, 0) + 1
            rows.append({"team": team, "name": name, "number": int(number), "school": school_of[team], "pitcher": f"{school_of[team]}-P{rank:02d}", "label": f"#{number}{suffix}"})
    return pd.DataFrame(rows).sort_values(["school", "pitcher"], ignore_index=True)


def input_rows(table: pd.DataFrame, names: pd.DataFrame, competition: pd.Series, rounds: dict[str, int] | None) -> pd.DataFrame:
    """고교 모듈 입력표 형식(row, date, competition, game_no, school, pitcher, pitches, outs)에 열을 더한 표. 선수 실명은 들어가지 않는다.
    competition: 경기(game_idx) → 대회 이름. game_no는 경기 순서(1~), round는 rounds(라운드 이름 → 경기 수)를 순서대로 배정한 것(없으면 NaN)."""
    key = names.set_index(["team", "name", "number"])
    codes = key.loc[list(zip(table["team"], table["name"], table["number"]))].reset_index(drop=True)
    games = sorted(table["game_idx"].unique(), key=lambda g: (table.loc[table["game_idx"] == g, "date"].iloc[0], g))
    round_of: dict = {}
    if rounds:
        labels = [name for name, count in rounds.items() for _ in range(count)]
        if len(labels) != len(games):
            raise ValueError(f"라운드 경기 수 합 {len(labels)} ≠ 경기 수 {len(games)}")
        round_of = dict(zip(games, labels))
    out = pd.DataFrame({
        "row": range(2, len(table) + 2), "date": table["date"].to_numpy(), "competition": table["game_idx"].map(competition).to_numpy(),
        "game_no": table["game_idx"].map({g: i + 1 for i, g in enumerate(games)}).to_numpy(),
        "school": codes["school"].to_numpy(), "pitcher": codes["pitcher"].to_numpy(),
        "pitches": table["pitches"].astype("Float64").astype(float).to_numpy(), "outs": table["outs"].astype(int).to_numpy(),
        "opponent": table["opponent"].to_numpy(), "role": table["role"].to_numpy(), "result": table["result"].to_numpy(),
        "round": table["game_idx"].map(round_of).to_numpy() if round_of else np.nan, "game_idx": table["game_idx"].to_numpy(), "detail": table["detail"].to_numpy(),
        "stints": table["stints"].to_numpy() if "stints" in table else 1})
    return out.sort_values(["game_no", "school", "row"], ignore_index=True)


def annotate_outings(rows: pd.DataFrame, kbsa: dict) -> pd.DataFrame:
    """등판마다 직전 등판과의 간격(gap_days: 사이에 쉰 날 수), 직전 투구 수가 요구하는 휴식일(required_rest), 지켰는지(rest_ok),
    의무 휴식일(1일 이상)을 꼭 채우고 첫 가능일에 등판했는지(min_rest_exact; 휴식 0일 뒤 연투는 gap_days=0으로 따로 센다),
    누적 투구 수(cum_pitches; 모르는 경기 뒤는 NaN)."""
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
        return None if np.isnan(value) else round(float(value), 3)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _rec(frame: pd.DataFrame, columns: list[str]) -> list[dict]:
    return [{c: _clean(v) for c, v in zip(columns, row)} for row in frame[columns].itertuples(index=False)]


def _chronic_at_flags(daily: pd.DataFrame) -> pd.Series:
    """ACWR 표시가 켜진 날의 직전 3주 주평균 투구 수(= 7일 합 ÷ ACWR). ACWR이 저활동 뒤에 튀는 성질을 보여 주는 맥락 값."""
    f = daily[daily["acwr_flag"] & (daily["acwr"] > 0)]
    return f["sum_7d"] / f["acwr"]


def payload(outings: pd.DataFrame, daily: pd.DataFrame, violated: pd.DataFrame, names: pd.DataFrame, rules: dict, info: dict, source: str) -> dict:
    """대시보드 highschool/<key>.json. 학교는 실명(names의 team), 투수는 등번호 표기(label)만 들어간다.
    mode == 'tournament'면 대회 누적·휴식 간격 중심, 'season'이면 ACWR(누적 부하) 중심의 값을 더한다."""
    kbsa_rules = set(hs.KBSA_RULES)
    flag = rules["acwr"]["flag"]
    school_name = names.drop_duplicates("school").set_index("school")["team"]
    label_of = names.set_index("pitcher")["label"]
    games = (outings.sort_values("game_no").groupby("game_no").agg(date=("date", "first"), competition=("competition", "first"), round=("round", "first"),
                                                                    detail=("detail", "first"), teams=("school", lambda s: sorted(school_name[c] for c in s.unique())),
                                                                    opponents=("opponent", lambda s: sorted(set(s))))
             .reset_index())
    game_list = [{"no": int(g.game_no), "date": _clean(g.date), "competition": g.competition, "round": _clean(g.round), "detail": bool(g.detail),
                  "teams": sorted(set(g.teams) | set(g.opponents))} for g in games.itertuples()]
    schools = []
    for school, mine in outings.groupby("school"):
        pitchers = []
        for code, g in mine.groupby("pitcher"):
            g = g.sort_values(["date", "game_no"])
            v = violated[violated["pitcher"] == code]
            real = v[v["rule"].isin(kbsa_rules)]
            status = "위반" if len(real) else ("판정 불가" if (v["rule"] == "unknown").any() else "준수")
            known = g["pitches"].notna().all()
            d = daily[daily["pitcher"] == code]
            peak = d.loc[d["acwr_ok"], "acwr"].max()
            load_status = ("경보" if d["acwr_flag"].any() else "주의" if peak >= 1.0 else "보통") if np.isfinite(peak) else "계산 불가"
            shown = d[(d["pitches"].fillna(0) != 0) | d["unknown"] | d["acwr_ok"]]
            pitchers.append({"code": code, "label": label_of[code], "rule_status": status, "load_status": load_status, "acwr_peak": _clean(peak),
                             "max_7d": _clean(d["sum_7d"].max()), "outings": int(len(g)), "pitches_total": int(g["pitches"].sum()) if known else None, "max_pitches": _clean(g["pitches"].max()),
                             "back_to_back": int((g["gap_days"] == 0).sum()), "min_rest_exact": int((g["min_rest_exact"] == True).sum()),
                             "violations": _rec(v, ["date", "rule", "detail"]), "games": _rec(g, GAME_COLUMNS),
                             "days": [{**r, "acwr": r["acwr"] if ok else None} for r, ok in zip(_rec(shown, DAY_COLUMNS), shown["acwr_ok"])]})
        pitchers.sort(key=lambda p: (-(p["pitches_total"] if p["pitches_total"] is not None else -1), p["label"]))
        schools.append({"code": school, "name": school_name[school], "games": int(mine["game_no"].nunique()), "outings": int(len(mine)),
                        "pitches_total": int(mine["pitches"].sum()) if mine["pitches"].notna().all() else None, "pitchers": pitchers})
    schools.sort(key=lambda s: (-s["games"], s["name"]))
    second = outings[outings["gap_days"].notna()]
    ordered = outings.sort_values(["pitcher", "date", "game_no"])
    two_day = ordered["pitches"] + ordered.groupby("pitcher")["pitches"].shift(1)                 # 연투 이틀 합 (직전 등판이 어제일 때만 뜻이 있음)
    heavy_b2b = int(((ordered["gap_days"] == 0) & (two_day >= 70)).sum())
    per = daily.groupby("pitcher").agg(ok=("acwr_ok", "any"), flag=("acwr_flag", "any"))
    per["violations"] = per.index.map(violated[violated["rule"].isin(kbsa_rules)].groupby("pitcher").size()).fillna(0).astype(int)
    totals = {"schools": int(outings["school"].nunique()), "pitchers": int(outings["pitcher"].nunique()), "outings": int(len(outings)),
              "games": int(outings["game_no"].nunique()), "unknown_outings": int(outings["pitches"].isna().sum()),
              "violations": int(violated["rule"].isin(kbsa_rules).sum()), "violating_pitchers": int((per["violations"] > 0).sum()),
              "violations_by_rule": {k: int(v) for k, v in violated["rule"].value_counts().items()},
              "rest_violations": int((second["rest_ok"] == False).sum()), "back_to_back": int((second["gap_days"] == 0).sum()), "back_to_back_70": heavy_b2b,
              "min_rest_exact": int((second["min_rest_exact"] == True).sum()),
              "games_100plus": int((outings["pitches"] >= 100).sum()), "games_91plus": int((outings["pitches"] >= 91).sum()),
              "pitchers_3plus_games": int((outings.groupby("pitcher").size() >= 3).sum()),
              "max_total": _clean(outings.groupby("pitcher")["pitches"].sum(min_count=1).max()),
              "acwr_ok_pitchers": int(per["ok"].sum()), "acwr_flag_pitchers": int(per["flag"].sum()),
              "compliant_with_flag": int(((per["violations"] == 0) & per["flag"]).sum()),
              "acwr_flag_chronic_median": _clean(_chronic_at_flags(daily).median()) if daily["acwr_flag"].any() else None,
              "pitchers_7d_150": int((daily.groupby("pitcher")["sum_7d"].max() >= 150).sum()),
              "pitchers_season_500": int((outings.groupby("pitcher")["pitches"].sum(min_count=1) >= 500).sum())}
    no_detail = sorted(int(g) for g in outings.loc[~outings["detail"], "game_no"].unique())
    first, last = outings["date"].min(), outings["date"].max()
    dataset = {"key": info.get("key"), "mode": info["mode"], "name": info["name"], "short": info["short"], "season": info["season"], "region": info.get("region"),
               "dates": info.get("dates") or f"{first:%Y-%m-%d} ~ {last:%Y-%m-%d}", "source": source,
               "games": int(outings["game_no"].nunique()), "no_detail_games": no_detail,
               "competitions": {k: int(v) for k, v in outings.drop_duplicates("game_no")["competition"].value_counts().items()}}
    return {"synthetic": False, "mode": info["mode"], "season": rules["season"], "acwr_flag": flag, "kbsa": rules["kbsa"],
            "foreign_rules": {k: v for k, v in rules["foreign_rules"].items() if v},
            "dataset": dataset, "games": game_list, "schools": schools, "totals": totals,
            "summary": [{k: _clean(v) for k, v in r.items()} for r in hs.summary(daily, violated).assign(**{"학교명": lambda d: d["학교"].map(school_name)}).to_dict("records")]}
