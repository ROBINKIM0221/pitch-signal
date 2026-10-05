"""기준선 구간 규칙 (SPEC 3.7). 부하 채널(2.5)·사례 확정(2.6)·감시(4.1)가 같이 쓴다.

선발(SP): 그 시즌 첫 starter_outings개 적격 등판.
불펜(RP): 그 시즌 첫 reliever_outings개 적격 등판과 주력 패스트볼 누적 reliever_min_fastballs구 중 늦은 시점까지.
규칙을 못 채운 투수-시즌은 기준선이 없다(직전 시즌 기록으로 대체하지 않음).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ORDER = ["pitcher", "season", "game_date", "game_pk"]


def _baseline_length(eligible: pd.DataFrame, rules: dict) -> int:
    """한 투수-시즌의 적격 등판(시간순)에서 기준선에 들어갈 등판 수. 규칙을 못 채우면 0."""
    if eligible["role"].iloc[0] == "SP":
        need = rules["starter_outings"]
    else:
        enough = (eligible["n_fb"].cumsum() >= rules["reliever_min_fastballs"]).to_numpy()
        if not enough.any():
            return 0
        need = max(rules["reliever_outings"], int(enough.argmax()) + 1)
    return need if len(eligible) >= need else 0


def _lengths(outings: pd.DataFrame, rules: dict) -> pd.Series:
    eligible = outings[outings["eligible"]].sort_values(ORDER)
    return eligible.groupby(["pitcher", "season"]).apply(_baseline_length, rules, include_groups=False)


def baseline_windows(outings: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """투수-시즌별 기준선: 등판 수, 등판 목록(game_pk), 마지막 기준선 등판일, 누적 주력 패스트볼 수."""
    lengths = _lengths(outings, rules)
    rows = []
    for (pitcher, season), group in outings.sort_values(ORDER).groupby(["pitcher", "season"]):
        n = int(lengths.get((pitcher, season), 0))
        base = group[group["eligible"]].iloc[:n]
        rows.append({"pitcher": pitcher, "season": season, "role": group["role"].iloc[0], "n_baseline": n,
                     "baseline_games": base["game_pk"].tolist(),
                     "baseline_end": base["game_date"].max() if n else pd.NaT, "n_fb_baseline": int(base["n_fb"].sum())})
    return pd.DataFrame(rows)


def phase(outings: pd.DataFrame, rules: dict) -> pd.Series:
    """등판마다 'baseline'(기준선), 'monitor'(기준선 뒤 적격 등판), ''(그 밖)를 붙인다. 순서는 outings 그대로."""
    o = outings.reset_index(drop=True)
    eligible = o[o["eligible"]].sort_values(ORDER)
    rank = eligible.groupby(["pitcher", "season"]).cumcount().to_numpy()
    lengths = _lengths(o, rules)
    n = pd.MultiIndex.from_frame(eligible[["pitcher", "season"]]).map(lengths).to_numpy()
    out = np.full(len(o), "", dtype=object)
    out[eligible.index[rank < n]] = "baseline"
    out[eligible.index[(rank >= n) & (n > 0)]] = "monitor"
    return pd.Series(out, index=outings.index)
