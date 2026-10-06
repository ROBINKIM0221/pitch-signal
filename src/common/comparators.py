"""비교 대상 B1~B4 (SPEC 3.12). 07_comparators·08_evaluate·09_sealed가 같이 쓴다.

  B1 구속 하락 규칙: 등판 평균 구속 < 시작 구간 평균 − velo_drop_mph (고정 임계)
  B2 WHIP CUSUM:     등판 WHIP를 시작 구간 평균·표준편차로 표준화한 상방 CUSUM (k), 경보 뒤 0에서 다시
  B3 마할라노비스:   직전 window개 적격 등판의 평균·공분산(예측 오차 표준편차의 대각으로 shrink만큼 수축) 대비 거리
  B4 구속 EWMA:      구속만의 표준화 예측 오차(uv)에 양방향 EWMA (core의 monitor 그대로)
'기준선(baseline)'과 헷갈리지 않게 이들은 comparator라고 부른다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import calibration as cal
from src.core import stats_core as sc

OUTING = ["pitcher", "season", "game_pk"]
ORDER = ["pitcher", "season", "game_date", "game_pk"]


def whip(outings: pd.DataFrame, floor_outs: int, cap: float) -> pd.Series:
    """등판 WHIP = (피안타 + 볼넷) ÷ (아웃 ÷ 3). 아웃이 floor_outs개 미만이면 그 값으로, cap을 넘으면 cap으로."""
    return ((outings["h"] + outings["bb"]) / (outings["outs"].clip(lower=floor_outs) / 3)).clip(upper=cap)


def b2_cusum(w: np.ndarray, k: float, h: float) -> tuple[np.ndarray, np.ndarray]:
    """표준화한 WHIP 수열의 상방 CUSUM: S_t = max(0, S_{t−1} + w_t − k). S_t > h면 경보, 경보 뒤 S = 0."""
    s, alarm, value = np.zeros(len(w)), np.zeros(len(w), dtype=bool), 0.0
    for t, x in enumerate(w):
        value = max(0.0, value + x - k)
        s[t] = value
        if value > h:
            alarm[t], value = True, 0.0
    return alarm, s


def b3_distance(x: np.ndarray, sd: np.ndarray, window: int, shrink: float) -> np.ndarray:
    """등판마다 직전 window개 등판의 평균·공분산 대비 마할라노비스 거리 D². 앞 window개는 NaN.

    공분산은 표본 공분산을 (1 − shrink), 그 등판의 예측 오차 표준편차 제곱의 대각을 shrink만큼 섞은 것이다.
    """
    d2 = np.full(len(x), np.nan)
    for t in range(window, len(x)):
        if np.isnan(sd[t]).any():
            continue
        past = x[t - window:t]
        cov = (1 - shrink) * np.cov(past, rowvar=False) + shrink * np.diag(sd[t] ** 2)
        d = x[t] - past.mean(axis=0)
        d2[t] = float(d @ np.linalg.solve(cov, d))
    return d2


def b4_ewma(uv: np.ndarray, h: float, lam: float) -> tuple[np.ndarray, np.ndarray]:
    """구속만의 양방향 EWMA (경보 뒤 다시 시작). (경보 여부, 통계량 Q)."""
    chart = sc.monitor(uv, h, np.inf, lam)
    return chart.alarm, chart.q


def threshold_for_rate(flags_for, target: float, tol: float = 0.01) -> float:
    """flags_for(한계) → 투수-시즌별 경보 배열 목록. 100등판당 경보가 target 이하가 되는 가장 낮은 한계."""
    return cal.lowest_limit(lambda h: cal.false_alarms_per100(flags_for(h)), target, tol)


def statistics(outings: pd.DataFrame, monitored: pd.DataFrame, features: list[str], rules: dict,
               whip_cap: float) -> pd.DataFrame:
    """감시 등판마다 비교 대상의 통계량: b1_drop(mph), b2_w(표준화 WHIP), b3_d2, uv.

    outings: phase 열이 있는 등판 표(시작 구간 'baseline'). monitored: 감시 등판의 pitcher, season, game_pk, uv, sd_<특징>.
    시작 구간의 평균 구속, WHIP 평균·표준편차를 투수-시즌별 기준으로 쓴다. WHIP 표준편차가 0이면 같은 표 안 다른 투수-시즌들의 중앙값으로 대신한다.
    """
    o = outings.sort_values(ORDER).copy()
    o["whip"] = whip(o, rules["B2"]["ip_floor_outs"], whip_cap)
    start = o[o["phase"] == "baseline"].groupby(["pitcher", "season"]).agg(
        start_velo=("velo", "mean"), whip_mean=("whip", "mean"), whip_sd=("whip", "std"))
    positive = start["whip_sd"][start["whip_sd"] > 0]
    start["whip_sd"] = start["whip_sd"].where(start["whip_sd"] > 0, positive.median())
    eligible = o[o["eligible"]].merge(monitored[[*OUTING, "uv", *[f"sd_{f}" for f in features]]], on=OUTING, how="left")
    parts = []
    for (pitcher, season), g in eligible.groupby(["pitcher", "season"], sort=False):
        if g["uv"].isna().all():                                  # 감시 등판이 없는 투수-시즌 (시작 구간을 못 채움)
            continue
        s = start.loc[(pitcher, season)]
        part = g[[*OUTING, "role", "game_date", "uv"]].copy()
        part["b1_drop"] = s["start_velo"] - g["velo"]
        part["b2_w"] = (g["whip"] - s["whip_mean"]) / s["whip_sd"]
        part["b3_d2"] = b3_distance(g[features].to_numpy(dtype=float), g[[f"sd_{f}" for f in features]].to_numpy(dtype=float),
                                    rules["B3"]["window"], rules["B3"]["shrink_to_baseline_diag"])
        parts.append(part[part["uv"].notna()])                      # 감시 등판만 남긴다
    return pd.concat(parts, ignore_index=True)


def alarms(stats: pd.DataFrame, limits: dict, rules: dict, lam: float) -> pd.DataFrame:
    """통계량 표에 비교 대상별 경보(b<n>_alarm)와 지수(b<n>_index, 1 이상이면 경보)를 붙인다.

    limits: {"B2": {역할: h}, "B3": {역할: d2 한계}, "B4": {역할: h}}. B1은 rules["B1"]["velo_drop_mph"]의 고정 임계.
    """
    out = stats.copy()
    out["b1_index"] = out["b1_drop"] / rules["B1"]["velo_drop_mph"]
    out["b1_alarm"] = out["b1_index"] > 1
    out["b3_index"] = out["b3_d2"] / out["role"].map(limits["B3"])
    out["b3_alarm"] = out["b3_index"] > 1
    for name in ("b2", "b4"):
        out[f"{name}_alarm"], out[f"{name}_index"] = False, 0.0
    for rows in out.groupby(["pitcher", "season"], sort=False).indices.values():
        part = out.iloc[rows]
        role = part["role"].iloc[0]
        alarm, s = b2_cusum(part["b2_w"].to_numpy(dtype=float), rules["B2"]["cusum_k"], limits["B2"][role])
        out.iloc[rows, out.columns.get_loc("b2_alarm")], out.iloc[rows, out.columns.get_loc("b2_index")] = alarm, s / limits["B2"][role]
        alarm, q = b4_ewma(part["uv"].to_numpy(dtype=float), limits["B4"][role], lam)
        out.iloc[rows, out.columns.get_loc("b4_alarm")], out.iloc[rows, out.columns.get_loc("b4_index")] = alarm, q / limits["B4"][role]
    return out
