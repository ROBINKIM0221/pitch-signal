"""불펜 부하 채널 지표 (SPEC 3.11). 투구 품질과 따로, 전 구종 투구 수로 사용 패턴을 본다."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.core import kbsa_rules as kr


def load_metrics(outings: pd.DataFrame, rules: dict, baseline_end) -> pd.DataFrame:
    """한 투수-시즌의 등판(game_pk, game_date, n_all)마다 부하 지표와 표시(flag_*)를 붙여 돌려준다.

    같은 날 두 번 던졌으면 그날 값을 합쳐 계산한다. baseline_end는 그 투수의 기준선 마지막 등판일이며,
    7일 투구 수 표시는 그날까지의 본인 값 백분위를 넘을 때만 켠다(기준선이 없으면 켜지 않음).
    """
    log = outings.rename(columns={"game_date": "date", "n_all": "pitches"})
    daily = kr.daily_series(log)                                       # 날짜별 투구 수, 등판 없는 날은 0
    apps = log.groupby("date").size().reindex(daily.index, fill_value=0)
    pitched = apps > 0
    last = pd.Series(daily.index.where(pitched), index=daily.index).ffill().shift(1)      # 직전 등판일
    day = pd.DataFrame({
        "back_to_back": pitched & pitched.shift(1, fill_value=False),
        "consecutive_days": pitched.groupby((~pitched).cumsum()).cumsum(),
        "apps_3d": apps.rolling(3, min_periods=1).sum().astype(int),
        "p7d": daily.rolling(rules["acute_days"], min_periods=1).sum(),
        "acwr": kr.acwr(daily, rules["acute_days"], rules["chronic_days"])["acwr"],
        "prev_pitches": last.map(daily),
        "rest_days": (daily.index.to_series() - last).dt.days - 1,
    })
    limit = np.nan
    if not pd.isna(baseline_end):
        limit = np.percentile(day.loc[pitched & (daily.index <= baseline_end), "p7d"], rules["p7d_percentile"])
    day["flag_consecutive"] = day["consecutive_days"] >= rules["consecutive_days_flag"]
    day["flag_apps_3d"] = day["apps_3d"] >= rules["apps_3d_flag"]
    day["flag_p7d"] = day["p7d"] > limit
    day["flag_acwr"] = day["acwr"] > rules["acwr_flag"]
    day["flag_long_short"] = ((day["prev_pitches"] >= rules["long_outing_pitches"])
                              & (day["rest_days"] <= rules["short_rest_days"]))
    return outings[["game_pk", "game_date"]].merge(day, left_on="game_date", right_index=True, how="left")


def load_table(outings: pd.DataFrame, windows: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """모든 투수-시즌의 등판별 부하 지표. windows는 baseline_window.baseline_windows의 결과."""
    ends = windows.set_index(["pitcher", "season"])["baseline_end"]
    parts = []
    for (pitcher, season), group in outings.groupby(["pitcher", "season"]):
        m = load_metrics(group, rules, ends.get((pitcher, season), pd.NaT))
        m.insert(0, "season", season)
        m.insert(0, "pitcher", pitcher)
        parts.append(m)
    return pd.concat(parts, ignore_index=True)
