"""개발셋 실측 보정 (SPEC 3.9의 2·3). 06_monitor·08_evaluate·09_sealed가 같이 쓴다.

경보 규칙은 두 가지다.
  기본형: T² > T² 한계 또는 3개 특징 MEWMA > h
  결합형: 기본형 + 구속 하나의 EWMA > h_velo. 어느 규칙이든 울리면 두 EWMA를 함께 0에서 다시 시작한다
T²·MEWMA 계산은 src/core/stats_core.monitor를 그대로 쓴다. 한 투수-시즌은 (u, uv)로 넘긴다:
u는 표준화한 예측 오차(등판 수 × 특징 수), uv는 구속 하나로 같은 계산을 한 값(등판 수).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.core import stats_core as sc

FIRST_GUESS = 16.0      # 한계를 찾기 시작하는 값 (넘으면 두 배씩 늘린다)


@dataclass(frozen=True)
class Rule:
    lam: float                      # EWMA 평활 상수 λ
    t2: float                       # T² 한계
    h: float                        # 3개 특징 MEWMA 한계
    h_velo: float | None = None     # 결합형이면 구속 EWMA 한계, 기본형이면 None


def alarms(u: np.ndarray, uv: np.ndarray, rule: Rule) -> np.ndarray:
    """한 투수-시즌의 등판별 경보 여부."""
    if rule.h_velo is None:
        return sc.monitor(u, rule.h, rule.t2, rule.lam).alarm
    alarm, start = np.zeros(len(u), dtype=bool), 0
    while start < len(u):               # 다음 경보까지 두 관리도를 따로 돌리고, 먼저 울린 곳에서 함께 다시 시작
        either = (sc.monitor(u[start:], rule.h, rule.t2, rule.lam, reset_after_alarm=False).alarm
                  | sc.monitor(uv[start:], rule.h_velo, np.inf, rule.lam, reset_after_alarm=False).alarm)
        if not either.any():
            break
        start += int(either.argmax()) + 1
        alarm[start - 1] = True
    return alarm


def _per100(flags: list[np.ndarray]) -> float:
    return 100.0 * sum(int(f.sum()) for f in flags) / sum(len(f) for f in flags)


def false_alarms_per100(seasons: list[tuple], rule: Rule) -> float:
    """여러 투수-시즌(대조군)에서 100등판당 경보 수."""
    return _per100([alarms(u, uv, rule) for u, uv in seasons])


def t2_limit(t2: np.ndarray, start: float, max_per100: float) -> float:
    """T² 한계. 이론값 start를 쓰되, T²만으로 100등판당 max_per100번 넘게 울리면 딱 그만큼만 넘는 값으로 올린다."""
    if 100 * (t2 > start).mean() <= max_per100:
        return start
    allowed = int(np.floor(len(t2) * max_per100 / 100))
    return float(np.sort(t2)[-(allowed + 1)])


def _lowest_limit(per100, target: float, tol: float) -> float:
    """per100(h) ≤ target이 되는 가장 작은 h (오차 tol). per100은 h가 커질수록 줄어든다고 본다."""
    lo, hi = 0.0, FIRST_GUESS
    while per100(hi) > target:
        lo, hi = hi, 2 * hi
    while hi - lo > tol:
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if per100(mid) <= target else (mid, hi)
    return hi


def fit_basic(seasons: list[tuple], lam: float, t2: float, target: float, tol: float = 0.01) -> Rule:
    """기본형: 대조군 실측 오경보가 100등판당 target 이하가 되는 가장 낮은 h."""
    h = _lowest_limit(lambda h: false_alarms_per100(seasons, Rule(lam, t2, h)), target, tol)
    return Rule(lam, t2, h)


def fit_union(seasons: list[tuple], lam: float, t2: float, target: float, tol: float = 0.01) -> Rule:
    """결합형: 두 EWMA 규칙의 단독 실측 오경보율을 같게 두면서 규칙 전체가 100등판당 target 이하가 되게 한다.

    단독 오경보율 r을 정하면 두 한계가 정해진다(각 EWMA만 썼을 때 100등판당 r). 전체가 target을 넘지 않는
    가장 큰 r을 이분법으로 찾는다. tol은 한계와 r 양쪽에 쓰는 허용 오차다.
    """
    def alone(index):
        return lambda h: _per100([sc.monitor(s[index], h, np.inf, lam).alarm for s in seasons])

    def at(r):
        return Rule(lam, t2, _lowest_limit(alone(0), r, tol), _lowest_limit(alone(1), r, tol))

    lo, hi, best = 0.0, target, None
    while hi - lo > tol:
        mid = (lo + hi) / 2
        rule = at(mid)
        if false_alarms_per100(seasons, rule) <= target:
            lo, best = mid, rule
        else:
            hi = mid
    return best if best is not None else at(lo)


def sequences(table: pd.DataFrame, features: list[str]) -> list[tuple]:
    """표준화한 표(시간순)를 투수-시즌별 (u, uv) 목록으로 나눈다."""
    columns = [f"u_{f}" for f in features]
    return [(part[columns].to_numpy(dtype=float), part["uv"].to_numpy(dtype=float))
            for _, part in table.groupby(["pitcher", "season"], sort=False)]


def table_alarms(table: pd.DataFrame, features: list[str], rule: Rule) -> np.ndarray:
    """표준화한 표(시간순)의 등판마다 경보 여부. 투수-시즌마다 새로 시작한다."""
    columns, alarm = [f"u_{f}" for f in features], np.zeros(len(table), dtype=bool)
    for rows in table.groupby(["pitcher", "season"], sort=False).indices.values():
        part = table.iloc[rows]
        alarm[rows] = alarms(part[columns].to_numpy(dtype=float), part["uv"].to_numpy(dtype=float), rule)
    return alarm
