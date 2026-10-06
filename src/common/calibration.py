"""두 신호의 경보 규칙과 개발셋 실측 보정 (SPEC 3.8~3.9). 06_monitor·08_evaluate·09_sealed가 같이 쓴다.

  구속 하락 신호: 구속만의 표준화한 예측 오차 uv에 한 방향 EWMA. s_t = √((2−λ)/λ)·z_t가 −k보다 낮으면 경보, 경보 뒤 z = 0.
                  지수 = −s_t / k (되돌리기 전 값). 1 이상이면 경보
  폼 변화 신호:   3개 특징의 표준화한 예측 오차 u에 T² + MEWMA (core의 monitor 그대로). 지수 = max(T²/T² 한계, Q/h)
한 투수-시즌은 (u 등판 수 × 특징 수, uv 등판 수)로 넘긴다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.core import stats_core as sc

FIRST_GUESS = 16.0      # 한계를 찾기 시작하는 값 (넘으면 두 배씩 늘린다)


@dataclass(frozen=True)
class VeloRule:
    lam: float
    k: float            # 표준화 EWMA 단위의 한 방향 한계


@dataclass(frozen=True)
class ChangeRule:
    lam: float
    t2: float           # T² 한계
    h: float            # MEWMA 한계


def velo_signal(uv: np.ndarray, rule: VeloRule) -> tuple[np.ndarray, np.ndarray]:
    """한 투수-시즌의 (경보 여부, 구속 하락 지수)."""
    scale, z = np.sqrt((2 - rule.lam) / rule.lam), 0.0
    alarm, index = np.zeros(len(uv), dtype=bool), np.zeros(len(uv))
    for t, value in enumerate(uv):
        z = rule.lam * value + (1 - rule.lam) * z
        index[t] = -scale * z / rule.k
        if index[t] > 1:
            alarm[t], z = True, 0.0
    return alarm, index


def change_signal(u: np.ndarray, rule: ChangeRule) -> tuple[np.ndarray, np.ndarray]:
    """한 투수-시즌의 (경보 여부, 폼 변화 지수)."""
    chart = sc.monitor(u, rule.h, rule.t2, rule.lam)
    return chart.alarm, np.maximum(chart.t2 / rule.t2, chart.q / rule.h)


def false_alarms_per100(flags: list[np.ndarray]) -> float:
    """여러 투수-시즌(대조군)의 경보 여부 배열에서 100등판당 경보 수."""
    return 100.0 * sum(int(f.sum()) for f in flags) / sum(len(f) for f in flags)


def t2_limit(t2: np.ndarray, start: float, max_per100: float) -> float:
    """T² 한계. 이론값 start를 쓰되, T²만으로 100등판당 max_per100번 넘게 울리면 딱 그만큼만 넘는 값으로 올린다."""
    if 100 * (t2 > start).mean() <= max_per100:
        return start
    allowed = int(np.floor(len(t2) * max_per100 / 100))
    return float(np.sort(t2)[-(allowed + 1)])


def _lowest_limit(per100, target: float, tol: float) -> float:
    """per100(한계) ≤ target이 되는 가장 작은 한계 (오차 tol). per100은 한계가 커질수록 줄어든다고 본다."""
    lo, hi = 0.0, FIRST_GUESS
    while per100(hi) > target:
        lo, hi = hi, 2 * hi
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if per100(mid) <= target else (mid, hi)
    return hi


def fit_velo(seasons: list[np.ndarray], lam: float, target: float, tol: float = 0.01) -> VeloRule:
    """구속 하락 신호: 대조군(uv 목록) 실측 오경보가 100등판당 target 이하가 되는 가장 낮은 k."""
    k = _lowest_limit(lambda k: false_alarms_per100([velo_signal(uv, VeloRule(lam, k))[0] for uv in seasons]), target, tol)
    return VeloRule(lam, k)


def fit_change(seasons: list[np.ndarray], lam: float, t2: float, target: float, tol: float = 0.01) -> ChangeRule:
    """폼 변화 신호: T² 한계를 고정한 채 대조군(u 목록) 실측 오경보가 100등판당 target 이하가 되는 가장 낮은 h."""
    h = _lowest_limit(lambda h: false_alarms_per100([change_signal(u, ChangeRule(lam, t2, h))[0] for u in seasons]), target, tol)
    return ChangeRule(lam, t2, h)


def theory_k(lam: float, target: float, n_sim: int, max_len: int, seed: int) -> float:
    """표준정규 입력에서 구속 하락 신호의 평균 런 길이가 target이 되는 k (이분법). core의 calibrate_h와 같은 방식."""
    x = np.random.default_rng(seed).standard_normal((n_sim, max_len))
    scale = np.sqrt((2 - lam) / lam)

    def arl(k):
        z, alive, length = np.zeros(n_sim), np.ones(n_sim, dtype=bool), np.full(n_sim, float(max_len))
        for t in range(max_len):
            z = lam * x[:, t] + (1 - lam) * z
            hit = alive & (scale * z < -k)
            length[hit], alive = t + 1, alive & ~hit
            if not alive.any():
                break
        return length.mean()

    lo, hi = 0.0, FIRST_GUESS
    while hi - lo > 0.005:
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if arl(mid) < target else (lo, mid)
    return hi


def sequences(table: pd.DataFrame, features: list[str]) -> list[tuple]:
    """표준화한 표(시간순)를 투수-시즌별 (u, uv) 목록으로 나눈다."""
    columns = [f"u_{f}" for f in features]
    return [(part[columns].to_numpy(dtype=float), part["uv"].to_numpy(dtype=float))
            for _, part in table.groupby(["pitcher", "season"], sort=False)]


def table_signals(table: pd.DataFrame, features: list[str], rules: dict) -> pd.DataFrame:
    """표준화한 표(시간순)에 두 신호의 경보와 지수를 붙인다: velo_alarm, velo_index, change_alarm, change_index.

    rules: {역할: (VeloRule, ChangeRule)}. 투수-시즌마다 새로 시작한다.
    """
    out, columns = table.copy(), [f"u_{f}" for f in features]
    new = {name: np.zeros(len(out), dtype=bool if name.endswith("alarm") else float)
           for name in ("velo_alarm", "velo_index", "change_alarm", "change_index")}
    for rows in out.groupby(["pitcher", "season"], sort=False).indices.values():
        part = out.iloc[rows]
        velo, change = rules[part["role"].iloc[0]]
        new["velo_alarm"][rows], new["velo_index"][rows] = velo_signal(part["uv"].to_numpy(dtype=float), velo)
        new["change_alarm"][rows], new["change_index"][rows] = change_signal(part[columns].to_numpy(dtype=float), change)
    return out.assign(**new)


def final_rules(cfg: dict) -> dict:
    """config_calibrated.yaml의 monitor.final(단계 4.5 결과)에서 역할별 (VeloRule, ChangeRule)을 만든다."""
    final = cfg["monitor"]["final"]
    return {role: (VeloRule(final["lam"], final["velo"][role]["k"]),
                   ChangeRule(final["lam"], final["change"][role]["t2"], final["change"][role]["h"]))
            for role in final["velo"]}
