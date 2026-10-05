"""사례와 대조군 확정 (SPEC 3.13.2). 관찰 창 규칙은 사례와 대조군에 똑같이 적용한다.

등판 표에는 baseline_window.phase로 붙인 phase 열('baseline' | 'monitor' | '')이 있어야 한다.
"""
from __future__ import annotations

import pandas as pd

KEY = ["pitcher", "season"]
DAYS_PER_YEAR = 365.25
CONTROL_COLUMNS = ["case_id", "pitcher", "season", "role", "index_date", "age", "cum_pitches", "dist", "window_games"]
SPLIT_NAMES = {"dev": "개발", "val": "검증", "sealed": "봉인"}


def window(o: pd.DataFrame, index_date: pd.Timestamp, rules: dict) -> tuple[list[int] | None, str]:
    """한 투수-시즌의 등판 표에서 관찰 창(기준일 전 마지막 window_outings개 감시 등판)의 game_pk 목록.

    쓸 수 없으면 (None, 이유). 감시 등판이 모자라거나, 마지막 등판이 기준일에서 너무 멀거나,
    창 안 등판 간격이 너무 길면(데이터가 끊긴 경우) 쓰지 않는다.
    """
    seen = o[(o["phase"] == "monitor") & (o["game_date"] < index_date)].sort_values(["game_date", "game_pk"])
    if len(seen) < rules["min_post_baseline_outings"]:
        return None, "감시 등판 부족"
    last = seen.tail(rules["window_outings"])
    if (index_date - last["game_date"].iloc[-1]).days > rules["max_days_last_outing_to_index"]:
        return None, "기준일 직전 등판 없음"
    if last["game_date"].diff().dt.days.max() > rules["max_gap_in_window_days"]:
        return None, "관찰 창 안 공백"
    return last["game_pk"].tolist(), ""


def _poorly_tracked(outings: pd.DataFrame, limit: float) -> set:
    """핵심 특징 결측 비율(등판별 core_missing_frac의 평균)이 limit를 넘는 투수-시즌."""
    frac = outings.groupby(KEY)["core_missing_frac"].mean()
    return set(frac[frac > limit].index)


def _birth_dates(people: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(people.set_index("id")["birth_date"])


def build_cases(raw: pd.DataFrame, outings: pd.DataFrame, people: pd.DataFrame,
                rules: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """투수-시즌별 첫 팔 부상 IL(raw) 중 관찰 창을 잡을 수 있는 것을 사례로 확정한다 → (사례, 빠진 것과 이유).

    case_id는 IL 기록 번호(event_id), 나이와 누적 투구 수(전 구종)는 기준일 기준이다.
    """
    born, poor = _birth_dates(people), _poorly_tracked(outings, rules["exclude_missing_tracking_frac"])
    by_season = dict(tuple(outings.groupby(KEY)))
    kept, dropped = [], []
    for r in raw.assign(il_date=pd.to_datetime(raw["il_date"])).itertuples(index=False):
        o = by_season.get((r.pitcher, r.season), outings.iloc[:0])
        games, why = (None, "트래킹 결측 과다") if (r.pitcher, r.season) in poor else window(o, r.il_date, rules)
        if games is None:
            dropped.append({"case_id": r.event_id, "pitcher": r.pitcher, "season": r.season, "il_date": r.il_date,
                            "why": why})
            continue
        kept.append({"case_id": r.event_id, "pitcher": r.pitcher, "season": r.season, "role": o["role"].iloc[0],
                     "part": r.part, "il_date": r.il_date, "age": (r.il_date - born[r.pitcher]).days / DAYS_PER_YEAR,
                     "cum_pitches": int(o.loc[o["game_date"] < r.il_date, "n_all"].sum()), "window_games": games})
    return pd.DataFrame(kept), pd.DataFrame(dropped)


def match_controls(cases: pd.DataFrame, outings: pd.DataFrame, il: pd.DataFrame, arm_il: pd.DataFrame,
                   people: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """사례마다 대조군을 controls_per_case명까지 고른다. 사례의 기준일이 대조군의 가상 기준일이 된다.

    후보: 같은 시즌·역할, 기준일 나이 차 age_tolerance세 이내, 기준일 앞뒤 control_il_free_days일 안에
    IL 기록(il: 부위와 상관없이 모든 등재)이 없고, 그 시즌에 팔 부상 IL(arm_il)이 없으며, 사례와 같은 규칙으로
    관찰 창을 잡을 수 있는 투수. 기준일까지 누적 투구 수가 가까운 순서로 고르고, 같으면 선수 번호가 작은 쪽.
    사례는 기준일이 이른 순서로 처리하며, 한 투수-시즌은 한 번만 쓴다.
    """
    born = _birth_dates(people)
    unavailable = (set(map(tuple, arm_il[KEY].to_numpy()))
                   | _poorly_tracked(outings, rules["exclude_missing_tracking_frac"]))
    free = pd.Timedelta(days=rules["control_il_free_days"])
    rows = []
    for c in cases.sort_values(["il_date", "pitcher"]).itertuples(index=False):
        pool = outings[(outings["season"] == c.season) & (outings["role"] == c.role)]
        cum = pool[pool["game_date"] < c.il_date].groupby("pitcher")["n_all"].sum()
        cand = pd.DataFrame({"cum_pitches": cum, "dist": (cum - c.cum_pitches).abs(),
                             "age": (c.il_date - born.reindex(cum.index)).dt.days / DAYS_PER_YEAR}).reset_index()
        on_il = set(il.loc[(il["il_date"] - c.il_date).abs() <= free, "pitcher"])
        cand = cand[((cand["age"] - c.age).abs() <= rules["age_tolerance"]) & ~cand["pitcher"].isin(on_il)]
        found = 0
        for x in cand.sort_values(["dist", "pitcher"]).itertuples(index=False):
            if (x.pitcher, c.season) in unavailable:
                continue
            games, _ = window(pool[pool["pitcher"] == x.pitcher], c.il_date, rules)
            if games is None:
                continue
            unavailable.add((x.pitcher, c.season))
            rows.append({"case_id": c.case_id, "pitcher": x.pitcher, "season": c.season, "role": c.role,
                         "index_date": c.il_date, "age": x.age, "cum_pitches": int(x.cum_pitches), "dist": int(x.dist),
                         "window_games": games})
            found += 1
            if found == rules["controls_per_case"]:
                break
    return pd.DataFrame(rows, columns=CONTROL_COLUMNS)


def window_table(cases: pd.DataFrame, controls: pd.DataFrame) -> pd.DataFrame:
    """관찰 창 등판을 한 줄에 하나씩: case_id, group('case' | 'control'), pitcher, season, game_pk."""
    both = pd.concat([cases.assign(group="case"), controls.assign(group="control")], ignore_index=True)
    long = both[["case_id", "group", "pitcher", "season", "window_games"]].explode("window_games", ignore_index=True)
    return long.rename(columns={"window_games": "game_pk"}).astype({"game_pk": "int64"})


def count_table(cases: pd.DataFrame, controls: pd.DataFrame, split: dict) -> pd.DataFrame:
    """시즌별·분할별 사례 수(역할·부위별)와 대조군 수, 대조군을 다 못 구한 사례 수."""
    got = cases["case_id"].map(controls.groupby("case_id").size()).fillna(0)
    flags = pd.DataFrame({"사례": 1, "선발": cases["role"] == "SP", "불펜": cases["role"] == "RP",
                          "팔꿈치": cases["part"] == "elbow", "어깨": cases["part"] == "shoulder", "대조군": got,
                          "대조군 1명뿐": got == 1, "대조군 없음": got == 0}, index=cases.index).astype(int)
    totals = {s: f"{SPLIT_NAMES[name]} 합계" for name, seasons in split.items() for s in seasons}
    by_split = flags.groupby(cases["season"].map(totals)).sum()
    by_split = by_split.loc[[t for t in dict.fromkeys(totals.values()) if t in by_split.index]]
    return pd.concat([flags.groupby(cases["season"].astype(str)).sum(), by_split]).rename_axis("시즌")
