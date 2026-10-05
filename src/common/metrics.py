"""평가 지표 (SPEC 3.13.3~3.13.4). 06_monitor(방식·λ 선택)·08_evaluate·09_sealed가 같이 쓴다."""
from __future__ import annotations

import numpy as np
import pandas as pd

OUTING = ["pitcher", "season", "game_pk"]


def window_results(windows: pd.DataFrame, monitored: pd.DataFrame) -> pd.DataFrame:
    """사례·대조군마다 관찰 창 안에서 경보가 울렸는지(hit)와 선행 등판 수(lead).

    windows: case_id, group, pitcher, season, game_pk (관찰 창 등판 한 줄에 하나)
    monitored: pitcher, season, game_pk, game_date, alarm (감시 등판마다 경보 여부)
    lead는 창 안 첫 경보 등판부터 창의 마지막 등판까지의 등판 수(경보 등판 포함), 경보가 없으면 NaN.
    """
    w = windows.merge(monitored[[*OUTING, "game_date", "alarm"]], on=OUTING, how="left", validate="many_to_one")
    if w["alarm"].isna().any():
        raise ValueError(f"감시 결과에 없는 관찰 창 등판이 {int(w['alarm'].isna().sum())}개 있습니다.")
    rows = []
    for (case_id, group, pitcher, season), g in w.sort_values("game_date").groupby(
            ["case_id", "group", "pitcher", "season"], sort=False):
        rang = g["alarm"].to_numpy(dtype=bool)
        rows.append({"case_id": case_id, "group": group, "pitcher": pitcher, "season": season, "hit": bool(rang.any()),
                     "lead": float(len(rang) - rang.argmax()) if rang.any() else np.nan})
    return pd.DataFrame(rows)


def detection(results: pd.DataFrame) -> dict:
    """탐지율(사례 중 창 안 경보 비율), 탐지 사례의 선행 등판 수 중앙값, 대조군 창 내 경보 비율."""
    cases, controls = results[results["group"] == "case"], results[results["group"] == "control"]
    return {"cases": len(cases), "detected": int(cases["hit"].sum()), "detection_rate": float(cases["hit"].mean()),
            "median_lead": float(cases["lead"].median()),
            "controls": len(controls), "control_window_rate": float(controls["hit"].mean())}
