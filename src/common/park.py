"""구장 보정 (SPEC 3.5). 구장마다 다른 측정 차이를 등판 평균에서 뺀다.

모형: 등판 평균 = 투수의 그 시즌 평균 + 구장 효과 + 나머지. 구장 효과는 구장 전체 평균이 0이 되게 잡는다.
그때 알 수 있던 값만 쓴다. 어떤 주(월~일)의 등판에는 그 주가 시작되기 전까지의 그 시즌 적격 등판으로 추정한 효과를 쓰고,
그 구장의 앞선 등판이 모자라면 직전 시즌 전체로 추정한 효과(그것도 없으면 0)를 쓴다.
등판 표의 열: pitcher, season, game_pk, game_date, venue(구장 번호), eligible, 그리고 보정할 특징.
"""
from __future__ import annotations

import pandas as pd

OUTING = ["pitcher", "season", "game_pk"]


def _usable(outings: pd.DataFrame, feature: str) -> pd.DataFrame:
    return outings[outings["eligible"] & outings[feature].notna() & outings["venue"].notna()]


def effects(outings: pd.DataFrame, feature: str, iterations: int) -> pd.Series:
    """한 시즌 등판들에서 구장별 효과(구장 번호 → 값). 투수 평균과 구장 평균을 번갈아 빼서 맞춘다."""
    d = _usable(outings, feature)
    by_venue, park = pd.Series(dtype=float), pd.Series(0.0, index=d.index)
    for _ in range(iterations):
        level = (d[feature] - park).groupby(d["pitcher"]).transform("mean")
        by_venue = (d[feature] - level).groupby(d["venue"]).mean()
        by_venue = by_venue - by_venue.mean()
        park = d["venue"].map(by_venue)
    return by_venue


def trusted_effects(outings: pd.DataFrame, feature: str, rules: dict) -> pd.Series:
    """구장별 효과 가운데 적격 등판이 min_prior_outings개 이상 쌓인 구장의 것만."""
    counts = _usable(outings, feature).groupby("venue").size()
    estimate = effects(outings, feature, rules["iterations"])
    return estimate[estimate.index.isin(counts.index[counts >= rules["min_prior_outings"]])]


def _season_adjustments(now: pd.DataFrame, feature: str, previous: pd.Series, rules: dict) -> pd.Series:
    """한 시즌의 등판마다 쓸 구장 효과. previous는 직전 시즌 전체로 추정한 효과."""
    week = now["game_date"] - pd.to_timedelta(now["game_date"].dt.weekday, unit="D")
    used = pd.Series(0.0, index=now.index)
    for start in sorted(week.unique()):
        so_far = trusted_effects(now[now["game_date"] < start], feature, rules)
        chosen = pd.concat([so_far, previous[~previous.index.isin(so_far.index)]])
        rows = week == start
        used[rows] = now.loc[rows, "venue"].map(chosen).fillna(0.0)
    return used


def adjustments(outings: pd.DataFrame, feature: str, rules: dict) -> pd.Series:
    """등판마다 빼 줄 구장 효과 (등판 표와 같은 순서). 시즌을 이른 순서로 처리한다."""
    used, previous = pd.Series(0.0, index=outings.index), pd.Series(dtype=float)
    for _, now in outings.groupby("season"):
        used[now.index] = _season_adjustments(now, feature, previous, rules)
        previous = trusted_effects(now, feature, rules)
    return used


def adjust(outings: pd.DataFrame, pitches_fb: pd.DataFrame, rules: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """rules['features']의 특징에서 구장 효과를 뺀 등판 표와 투구 표. 뺀 값은 등판 표의 park_<특징> 열에 남긴다."""
    o, fb = outings.copy(), pitches_fb.copy()
    for f in rules["features"]:
        o[f"park_{f}"] = adjustments(o, f, rules)
        o[f] = o[f] - o[f"park_{f}"]
        fb[f] = fb[f] - fb[OUTING].merge(o[[*OUTING, f"park_{f}"]], on=OUTING, how="left")[f"park_{f}"].to_numpy()
    return o, fb
