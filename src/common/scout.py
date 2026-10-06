"""영입 전 점검(화면 5): 한 투수의 MLB·트리플A 시즌을 요약한다. 자료 수집·실행은 src/16_scout.py가 한다."""
from __future__ import annotations

import numpy as np
import pandas as pd


def season_summary(table: pd.DataFrame) -> dict:
    """한 투수-시즌(등판 순)의 요약: 등판 수, 감시 등판 수, 시작 구간 평균 구속, 마지막 5등판 평균 구속, 그 차이, 경보 수, 첫 경보 날짜."""
    t = table.sort_values("game_date")
    base = t[t["phase"] == "baseline"]
    mon = t[t["phase"] == "monitor"]
    last5 = t.tail(5)
    first_alarm = mon.loc[mon["velo_alarm"] | mon["change_alarm"], "game_date"].min()
    fb = t["primary_fb"].mode().iloc[0] if "primary_fb" in t and t["primary_fb"].notna().any() else None
    return {"outings": int(len(t)), "monitored": int(len(mon)), "role": t["role"].iloc[0], "league": t["league"].iloc[0], "fb": fb,
            "velo_start": float(base["velo"].mean()) if len(base) else float("nan"),
            "velo_last5": float(last5["velo"].mean()), "velo_change": float(last5["velo"].mean() - base["velo"].mean()) if len(base) else float("nan"),
            "velo_max_index": float(mon["velo_index"].max()) if len(mon) else float("nan"),
            "alarms_velo": int(mon["velo_alarm"].sum()), "alarms_change": int(mon["change_alarm"].sum()),
            "first_alarm": None if pd.isna(first_alarm) else pd.Timestamp(first_alarm).strftime("%Y-%m-%d"),
            "first_date": pd.Timestamp(t["game_date"].iloc[0]).strftime("%Y-%m-%d"), "last_date": pd.Timestamp(t["game_date"].iloc[-1]).strftime("%Y-%m-%d")}


def arm_il(labels: pd.DataFrame, pitcher: int, season: int) -> dict | None:
    """그 투수-시즌의 첫 팔꿈치·어깨 IL (최종 라벨 기준). 없으면 None."""
    il = labels[(labels["pitcher"] == pitcher) & (labels["season"] == season) & labels["part"].isin(["elbow", "shoulder"])].sort_values("il_date")
    if il.empty:
        return None
    first = il.iloc[0]
    return {"date": pd.Timestamp(first["il_date"]).strftime("%Y-%m-%d"), "part": first["part"]}


def timeline(table: pd.DataFrame) -> list[dict]:
    """여러 시즌의 등판을 시간순으로 이어 붙인 구속 시계열 (리그·시즌·경보 표시 포함)."""
    t = table.sort_values(["game_date", "game_pk"])
    return [{"date": pd.Timestamp(r.game_date).strftime("%Y-%m-%d"), "season": int(r.season), "league": r.league, "velo": None if pd.isna(r.velo) else round(float(r.velo), 2),
             "alarm": bool(r.velo_alarm or r.change_alarm), "phase": r.phase, "velo_index": None if pd.isna(r.velo_index) else round(float(r.velo_index), 3)}
            for r in t.itertuples()]


def nan_to_none(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in d.items()}
