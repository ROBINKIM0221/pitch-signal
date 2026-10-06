"""평가 지표 (SPEC 3.13.3~3.13.4). 06_monitor(실측 보정 표)·08_evaluate·09_sealed가 같이 쓴다."""
from __future__ import annotations

import numpy as np
import pandas as pd

OUTING = ["pitcher", "season", "game_pk"]
SET = ["case_id", "group", "pitcher", "season"]


def window_results(windows: pd.DataFrame, monitored: pd.DataFrame, alarm: str = "alarm",
                   index: str | None = None) -> pd.DataFrame:
    """사례·대조군마다 관찰 창 안에서 경보가 울렸는지(hit), 선행 등판 수(lead), 창 지수(top: 창 안 지수의 최댓값).

    windows: case_id, group, pitcher, season, game_pk (관찰 창 등판 한 줄에 하나)
    monitored: pitcher, season, game_pk, game_date와 경보 열(alarm), 지수 열(index, 없으면 top을 만들지 않음)
    lead는 창 안 첫 경보 등판부터 창의 마지막 등판까지의 등판 수(경보 등판 포함), 경보가 없으면 NaN.
    """
    columns = [*OUTING, "game_date", alarm] + ([index] if index else [])
    w = windows.merge(monitored[columns], on=OUTING, how="left", validate="many_to_one")
    if w[alarm].isna().any():
        raise ValueError(f"감시 결과에 없는 관찰 창 등판이 {int(w[alarm].isna().sum())}개 있습니다.")
    rows = []
    for keys, g in w.sort_values("game_date").groupby(SET, sort=False):
        rang = g[alarm].to_numpy(dtype=bool)
        row = dict(zip(SET, keys))
        row.update(hit=bool(rang.any()), lead=float(len(rang) - rang.argmax()) if rang.any() else np.nan)
        if index:
            row["top"] = float(g[index].max())
        rows.append(row)
    return pd.DataFrame(rows)


def detection(results: pd.DataFrame) -> dict:
    """탐지율(사례 중 창 안 경보 비율), 탐지 사례의 선행 등판 수 중앙값, 대조군 창 내 경보 비율."""
    cases, controls = results[results["group"] == "case"], results[results["group"] == "control"]
    return {"cases": len(cases), "detected": int(cases["hit"].sum()), "detection_rate": float(cases["hit"].mean()),
            "median_lead": float(cases["lead"].median()),
            "controls": len(controls), "control_window_rate": float(controls["hit"].mean())}


def concordance(results: pd.DataFrame) -> pd.Series:
    """사례마다 '사례의 창 지수가 자기 대조군의 창 지수보다 큰 비율'(같으면 0.5). 대조군이 없는 사례는 뺀다.

    평균이 짝지은 일치도다: 0.5면 차이 없음, 1이면 사례가 늘 큼 (H1의 판정 지표, SPEC 3.13.4).
    """
    case_top = results[results["group"] == "case"].set_index("case_id")["top"]
    controls = results[results["group"] == "control"]
    mine = controls["case_id"].map(case_top)
    win = (mine > controls["top"]).astype(float) + 0.5 * (mine == controls["top"])
    return win.groupby(controls["case_id"]).mean().rename("concordance")


def bootstrap_ci(values: pd.Series, reps: int, seed: int) -> tuple[float, float, float]:
    """사례 단위 값들의 (평균, 95% 구간 하한, 상한). 사례를 복원 추출하는 백분위 부트스트랩."""
    x = values.to_numpy(dtype=float)
    draws = np.random.default_rng(seed).integers(0, len(x), size=(reps, len(x)))
    means = x[draws].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(x.mean()), float(lo), float(hi)
