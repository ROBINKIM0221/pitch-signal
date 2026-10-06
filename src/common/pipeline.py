"""어느 분할(개발·검증·봉인)이든 같은 순서로 감시 표를 만든다. 06_monitor·08_evaluate·09_sealed가 같이 쓴다.

시작 구간 적합(투수 본인) → 움직이는 기준선 표준화(개발셋에서 합동 추정한 역동) → 두 신호(최종 한계) → 비교 대상 B1~B4.
합동 추정값과 한계는 모두 config_calibrated.yaml에서 읽으므로, 개발셋이 아닌 시즌에는 어떤 값도 새로 맞추지 않는다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import baseline_window as bw
from src.common import calibration as cal
from src.common import comparators as cp
from src.common import monitoring as mon
from src.core import stats_core as sc

ROLES = ("SP", "RP")


def dynamics_from_config(cfg: dict) -> dict:
    """config_calibrated.yaml의 baseline.dynamics(단계 4.1 결과) → {역할: Dynamics}."""
    saved = cfg["baseline"]["dynamics"]
    return {role: mon.Dynamics(Q=np.array(saved[role]["Q"]), Se=np.array(saved[role]["Se"])) for role in ROLES}


def comparator_limits(cfg: dict) -> dict:
    """config_calibrated.yaml의 comparators(단계 5.1 결과) → cp.alarms가 받는 {"B2": {역할: h}, "B3": {역할: d2}, "B4": {역할: h}}."""
    saved = cfg["comparators"]
    return {"B2": {r: saved["B2"][r]["h"] for r in ROLES}, "B3": {r: saved["B3"][r]["d2"] for r in ROLES},
            "B4": {r: saved["B4"][r]["h"] for r in ROLES}}


def monitor_table(cfg: dict, outings: pd.DataFrame, pitches_fb: pd.DataFrame) -> pd.DataFrame:
    """주어진 시즌들의 감시 표: 표준화 값, 두 신호의 경보·지수, 비교 대상의 경보·지수 (투수-시즌 안에서 시간순)."""
    core, rules = cfg["features"]["core"], cfg["baseline"]
    arrays = mon.outing_arrays(pitches_fb, core)
    fits = mon.start_up_table(outings, arrays, rules)
    table = mon.dynamic_table(outings, fits, dynamics_from_config(cfg), rules, core, sc.t2_ucl(len(core), rules["refine_alpha"]))
    table = cal.table_signals(table, core, cal.final_rules(cfg))
    phased = outings.assign(phase=bw.phase(outings, rules).to_numpy())
    stats = cp.statistics(phased, table[[*cp.OUTING, "uv", *[f"sd_{f}" for f in core]]], core, cfg, cfg["comparators"]["B2"]["whip_cap"])
    marked = cp.alarms(stats, comparator_limits(cfg), cfg, cfg["monitor"]["lam"])
    columns = [c for c in marked.columns if c.startswith("b") and c[1].isdigit() and c[2] == "_"]
    return table.merge(marked[[*cp.OUTING, *columns]], on=cp.OUTING, how="left").sort_values(bw.ORDER).reset_index(drop=True)
