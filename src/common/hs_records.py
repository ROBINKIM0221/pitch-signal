"""KBSA 경기 기록 → 고교 모듈 입력표 → 등판별 휴식일 주석 → 대시보드 payload (시즌 모드·대회 모드).

선수 실명이 든 표(team, name, number)는 이 모듈 안에서만 다루고, 밖으로는 name_map()이 만든 대응표(저장소 밖에 저장)와
학교 실명·등번호 표기(#17)만 나간다. 규칙 계산은 src/core/kbsa_rules.py와 src/common/highschool.py를 그대로 쓴다.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from src.common import highschool as hs
from src.common import kbsa_boxscore as kb
from src.common.config import ROOT, _merge, load_config
from src.core import kbsa_rules as kr

GAME_KEY = ["game_idx", "team", "name", "number"]
GAME_COLUMNS = ["date", "game_no", "competition", "round", "opponent", "role", "result", "outs", "pitches", "detail", "gap_days", "required_rest", "rest_ok", "min_rest_exact", "cum_pitches",
                "batters", "k", "bb_hbp", "hits", "hr", "runs", "er"]


def datasets_config(root: Path = ROOT) -> tuple[dict, dict[str, tuple[dict, dict]]]:
    """config_kbsa.yaml → (공통 설정, {데이터셋 키: (데이터셋 설정, 고교 규칙)}). 규칙은 config.yaml highschool 블록에 overrides를 덮어쓴 것
    (schools 수는 변환 때 팀 수로 채운다)."""
    cfg = yaml.safe_load((Path(root) / "config_kbsa.yaml").read_text(encoding="utf-8"))
    base = load_config(root)["highschool"]
    return cfg, {key: (d, _merge(base, d["overrides"])) for key, d in cfg["datasets"].items()}


def flows_for_game(game: dict, batting: dict[str, list[dict]]) -> dict[tuple, list[dict]]:
    """한 경기의 '등판 흐름': 상대 타격표의 타석을 시간 순서로 펴서 이 팀 투수들에게 타자 수대로 나눠 준다.
    {(team, name, number): [{inn, res, cat, ev}, ...]} — 타석 수 합이 투수 타자 수 합과 다르면 그 팀 투수들은 비워 둔다.
    한 투수가 두 번 등판한 경기는 표의 두 줄이 각각 제 구간을 받으므로, 같은 열쇠에 이어 붙는다."""
    out: dict[tuple, list[dict]] = {}
    for team in game["teams"]:
        opponent = [t for t in game["teams"] if t != team]
        pitchers = [p for p in game["pitchers"] if p["team"] == team]
        if not pitchers or not opponent or opponent[0] not in batting:
            continue
        pas = kb.plate_appearances(batting[opponent[0]])
        parts = kb.assign_to_pitchers(pas, [p["batters"] or 0 for p in pitchers])
        if parts is None:
            continue
        for p, part in zip(pitchers, parts):
            key = (team, p["name"], p["number"])
            out.setdefault(key, []).extend({"inn": pa["inning"], "res": pa["result"], "cat": kb.pa_category(pa["result"]), "ev": pa["events"]} for pa in part)
    return out


WALK_EVENTS = ("폭투", "보크", "포일")


def flow_summary(flow: list[dict]) -> dict:
    """등판 흐름 요약: 타석 수, 삼진·4구·사구·안타·홈런, 4구+사구가 2개 이상 몰린 이닝, 폭투·보크·포일 수."""
    by_inning: dict[int, int] = {}
    for pa in flow:
        if pa["cat"] in ("BB", "HBP"):
            by_inning[pa["inn"]] = by_inning.get(pa["inn"], 0) + 1
    cats = [pa["cat"] for pa in flow]
    return {"pa": len(flow), "k": cats.count("K"), "bb": cats.count("BB"), "hbp": cats.count("HBP"), "h": cats.count("H") + cats.count("HR"), "hr": cats.count("HR"),
            "walk_innings": sorted(i for i, n in by_inning.items() if n >= 2), "wild": sum(sum(e in WALK_EVENTS for e in pa["ev"]) for pa in flow)}


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
           "result": lambda s: next((r for r in s if r in ("승", "패")), s.iloc[0]), "stints": "size",
           **{c: (lambda s: s.sum(min_count=1)) for c in kb.RESULT_COLUMNS if c in t.columns},
           **({"flow": "first"} if "flow" in t.columns else {})}
    out = (t.assign(stints=1).groupby(GAME_KEY, as_index=False, sort=False).agg(agg)
            .sort_values("_order").drop(columns="_order").reset_index(drop=True))
    for col in ["pitches", "batters", *[c for c in kb.RESULT_COLUMNS if c in out.columns]]:
        out[col] = out[col].astype("Int64")
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
        "stints": table["stints"].to_numpy() if "stints" in table else 1,
        "batters": table["batters"].astype("Float64").astype(float).to_numpy() if "batters" in table else np.nan,
        **{c: table[c].astype("Float64").astype(float).to_numpy() for c in ("k", "bb_hbp", "hits", "hr", "runs", "er") if c in table},
        **({"flow": table["flow"].to_numpy()} if "flow" in table else {})})
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


def pair3_max(g: pd.DataFrame) -> float:
    """한 투수의 등판(날짜순)에서 '3일 안 두 등판'의 합 중 최댓값. 그런 쌍이 없거나 투구 수를 모르면 NaN."""
    g = g.sort_values(["date", "game_no"])
    gaps = g["date"].diff().dt.days
    sums = g["pitches"] + g["pitches"].shift(1)
    close = sums[(gaps <= 2) & sums.notna()]
    return float(close.max()) if len(close) else np.nan


def load_light(max_7d, max_pair3, lights: dict) -> tuple[str, list[str]]:
    """누적 부하 신호등: 7일 합과 3일 안 두 등판 합을 절대량 기준(load_lights)에 대 본다. 어느 하나라도 '높음'이면 높음, '주의'만 있으면 주의."""
    reasons, level = [], 0
    for value, key, name in ((max_7d, "sum7", "7일 합"), (max_pair3, "pair3", "3일 안 두 등판 합")):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            continue
        if value >= lights[key]["high"]:
            level = max(level, 2); reasons.append(f"{name} {value:.0f}구 (높음 기준 {lights[key]['high']})")
        elif value >= lights[key]["caution"]:
            level = max(level, 1); reasons.append(f"{name} {value:.0f}구 (주의 기준 {lights[key]['caution']})")
    return ["보통", "주의", "높음"][level], reasons


def payload(outings: pd.DataFrame, daily: pd.DataFrame, violated: pd.DataFrame, names: pd.DataFrame, rules: dict, info: dict, source: str, lights: dict) -> dict:
    """대시보드 highschool/<key>.json. 학교는 실명(names의 team), 투수는 등번호 표기(label)만 들어간다.
    누적 부하 신호등은 절대량(load_lights: 7일 합, 3일 안 두 등판 합)으로 매기고, ACWR은 고교 화면에서 쓰지 않는다(2026-10-07 결정)."""
    kbsa_rules = set(hs.KBSA_RULES)
    school_name = names.drop_duplicates("school").set_index("school")["team"]
    label_of = names.set_index("pitcher")["label"]
    games = (outings.sort_values("game_no").groupby("game_no").agg(date=("date", "first"), competition=("competition", "first"), round=("round", "first"),
                                                                    detail=("detail", "first"), teams=("school", lambda s: sorted(school_name[c] for c in s.unique())),
                                                                    opponents=("opponent", lambda s: sorted(set(s))))
             .reset_index())
    game_list = [{"no": int(g.game_no), "date": _clean(g.date), "competition": g.competition, "round": _clean(g.round), "detail": bool(g.detail),
                  "teams": sorted(set(g.teams) | set(g.opponents))} for g in games.itertuples()]
    violations_of = violated[violated["rule"].isin(kbsa_rules)].groupby("pitcher").size()
    schools, per_rows = [], []
    for school, mine in outings.groupby("school"):
        pitchers = []
        for code, g in mine.groupby("pitcher"):
            g = g.sort_values(["date", "game_no"])
            v = violated[violated["pitcher"] == code]
            status = "위반" if violations_of.get(code, 0) else ("판정 불가" if (v["rule"] == "unknown").any() else "준수")
            known = g["pitches"].notna().all()
            d = daily[daily["pitcher"] == code]
            max_7d, max_pair3 = _clean(d["sum_7d"].max()), _clean(pair3_max(g))
            load_status, reasons = load_light(max_7d, max_pair3, lights)
            per_rows.append({"school": school, "pitcher": code, "violations": int(violations_of.get(code, 0)), "load": load_status})
            games_out = _rec(g, [c for c in GAME_COLUMNS if c in g.columns])
            if "flow" in g.columns:
                for rec, raw in zip(games_out, g["flow"]):
                    flow = json.loads(raw) if isinstance(raw, str) else None
                    rec["flow"] = [[pa["inn"], pa["res"], pa["cat"], *([pa["ev"]] if pa["ev"] else [])] for pa in flow] if flow else None   # 요약은 화면이 계산
            batters = g["batters"].sum(min_count=1) if "batters" in g else np.nan
            season_results = {c: _clean(g[c].sum(min_count=1)) for c in ("k", "bb_hbp", "hits", "hr") if c in g}
            pitchers.append({"code": code, "label": label_of[code], "rule_status": status, "load_status": load_status, "load_reasons": reasons,
                             "max_7d": max_7d, "max_pair3": max_pair3, "outings": int(len(g)),
                             "pitches_total": int(g["pitches"].sum()) if known else None, "max_pitches": _clean(g["pitches"].max()),
                             "back_to_back": int((g["gap_days"] == 0).sum()), "min_rest_exact": int((g["min_rest_exact"] == True).sum()),
                             "batters": _clean(batters), **season_results,
                             "p_per_pa": _clean(g["pitches"].sum() / batters) if known and pd.notna(batters) and batters > 0 else None,
                             "flow_games": int(g["flow"].notna().sum()) if "flow" in g else 0,
                             "violations": _rec(v, ["date", "rule", "detail"]), "games": games_out})
        pitchers.sort(key=lambda p: (-(p["pitches_total"] if p["pitches_total"] is not None else -1), p["label"]))
        span = daily.loc[daily["school"] == school, "date"]
        mine_rows = [r for r in per_rows if r["school"] == school]
        schools.append({"code": school, "name": school_name[school], "games": int(mine["game_no"].nunique()), "outings": int(len(mine)),
                        "pitches_total": int(mine["pitches"].sum()) if mine["pitches"].notna().all() else None,
                        "start": _clean(span.min()), "end": _clean(span.max()),                  # 수집 기간: 화면이 날짜별 7일 합을 다시 계산하는 범위
                        "violations": int(sum(r["violations"] for r in mine_rows)), "violating_pitchers": int(sum(r["violations"] > 0 for r in mine_rows)),
                        "load_high": int(sum(r["load"] == "높음" for r in mine_rows)), "load_caution": int(sum(r["load"] == "주의" for r in mine_rows)),
                        "compliant_with_load": int(sum(r["violations"] == 0 and r["load"] != "보통" for r in mine_rows)),
                        "pitchers": pitchers})
    schools.sort(key=lambda s: (-s["games"], s["name"]))
    per = pd.DataFrame(per_rows)
    second = outings[outings["gap_days"].notna()]
    ordered = outings.sort_values(["pitcher", "date", "game_no"])
    gaps = ordered.groupby("pitcher")["date"].diff().dt.days
    pair_sum = ordered["pitches"] + ordered.groupby("pitcher")["pitches"].shift(1)
    pairs = pair_sum[(gaps <= 2) & pair_sum.notna()]                                           # 3일 안 두 등판의 합
    heavy_b2b = int(((ordered["gap_days"] == 0) & (pair_sum >= 70)).sum())
    max7 = daily.groupby("pitcher")["sum_7d"].max()
    totals = {"schools": int(outings["school"].nunique()), "pitchers": int(outings["pitcher"].nunique()), "outings": int(len(outings)),
              "games": int(outings["game_no"].nunique()), "unknown_outings": int(outings["pitches"].isna().sum()),
              "violations": int(violated["rule"].isin(kbsa_rules).sum()), "violating_pitchers": int((per["violations"] > 0).sum()),
              "violations_by_rule": {k: int(v) for k, v in violated["rule"].value_counts().items()},
              "rest_violations": int((second["rest_ok"] == False).sum()), "back_to_back": int((second["gap_days"] == 0).sum()), "back_to_back_70": heavy_b2b,
              "min_rest_exact": int((second["min_rest_exact"] == True).sum()),
              "games_100plus": int((outings["pitches"] >= 100).sum()), "games_91plus": int((outings["pitches"] >= 91).sum()),
              "pitchers_3plus_games": int((outings.groupby("pitcher").size() >= 3).sum()),
              "max_total": _clean(outings.groupby("pitcher")["pitches"].sum(min_count=1).max()),
              "pitchers_load_high": int((per["load"] == "높음").sum()), "pitchers_load_caution": int((per["load"] == "주의").sum()),
              "compliant_with_load": int(((per["violations"] == 0) & (per["load"] != "보통")).sum()),
              "pairs3": int(len(pairs)), "pairs3_70": int((pairs >= lights["pair3"]["caution"]).sum()), "pairs3_100": int((pairs >= lights["pair3"]["high"]).sum()),
              "pitchers_7d_120": int((max7 >= lights["sum7"]["caution"]).sum()), "pitchers_7d_150": int((max7 >= lights["sum7"]["high"]).sum()),
              "pitchers_season_500": int((outings.groupby("pitcher")["pitches"].sum(min_count=1) >= 500).sum()),
              "flow_outings": int(outings["flow"].notna().sum()) if "flow" in outings else 0}
    no_detail = sorted(int(g) for g in outings.loc[~outings["detail"], "game_no"].unique())
    first, last = outings["date"].min(), outings["date"].max()
    dataset = {"key": info.get("key"), "mode": info["mode"], "name": info["name"], "short": info["short"], "season": info["season"], "region": info.get("region"),
               "dates": info.get("dates") or f"{first:%Y-%m-%d} ~ {last:%Y-%m-%d}", "source": source,
               "games": int(outings["game_no"].nunique()), "no_detail_games": no_detail,
               "competitions": {k: int(v) for k, v in outings.drop_duplicates("game_no")["competition"].value_counts().items()}}
    return {"synthetic": False, "mode": info["mode"], "season": rules["season"], "kbsa": rules["kbsa"], "load_lights": lights,
            "foreign_rules": {k: v for k, v in rules["foreign_rules"].items() if v},
            "dataset": dataset, "games": game_list, "schools": schools, "totals": totals}
