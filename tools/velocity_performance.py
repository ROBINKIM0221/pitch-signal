"""사후 분석(사전 등록 아님): 투수가 자기 예상보다 느리게 던진 등판에서 경기 결과가 실제로 나빠지는가.

감시 대상 등판(monitor_*.parquet)마다 Statcast 투구 기록으로 결과를 모아
  실점 가치(100구당, 타자 쪽 run value 합 — 클수록 투수에게 나쁨), 피wOBA, 삼진율, 볼넷+몸맞는공 비율, 헛스윙률
을 만들고, 같은 투수-시즌 안에서만 비교한다(투수-시즌 가중 평균을 빼는 회귀, 표준오차는 투수로 묶음).
노출은 두 가지: 구속 차이(등판 평균 주력 패스트볼 구속 − 그 등판 전 기준선의 예상값, mph)와 경보 여부.
경보 등판 다음 등판의 결과도 따로 본다. 결과는 reports/tables/velocity_performance.csv.

    python tools/velocity_performance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))        # 저장소 어디서 실행해도 src를 찾게
from src.common import metrics as mt  # noqa: E402
from src.common import statcast as st  # noqa: E402
from src.common.config import ROOT, load_config  # noqa: E402
from src.common.scout import SWING, WHIFF  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
COLUMNS = ["game_type", "pitcher", "game_pk", "delta_run_exp", "woba_value", "woba_denom", "events", "description"]
# 결과 열 → 가중치(분모) 열
OUTCOMES = {"rv100": "pitches", "woba": "woba_denom", "k_rate": "pa", "bb_rate": "pa", "whiff": "swings"}


def outing_results(cfg: dict) -> pd.DataFrame:
    frames = []
    for season in cfg["data"]["seasons"]:
        p = st.load_season(ROOT / "data" / "raw" / "statcast", season, COLUMNS)
        p = p[p["game_type"] == cfg["data"]["game_type"]]
        p = p.astype({"delta_run_exp": float, "woba_value": float, "woba_denom": float})   # 결측 가능 형식이면 0÷0이 결측으로 안 잡힌다
        d = p["description"].astype(str)
        p = p.assign(pa=p["events"].notna(), k=p["events"].isin(["strikeout", "strikeout_double_play"]),
                     bb=p["events"].isin(["walk", "hit_by_pitch"]), swings=d.isin(SWING), whiffs=d.isin(WHIFF))
        g = p.groupby(["pitcher", "game_pk"]).agg(pitches=("description", "size"), rv=("delta_run_exp", "sum"),
                                                  woba_num=("woba_value", "sum"), woba_denom=("woba_denom", "sum"),
                                                  pa=("pa", "sum"), k=("k", "sum"), bb=("bb", "sum"),
                                                  swings=("swings", "sum"), whiffs=("whiffs", "sum")).reset_index()
        frames.append(g)
    r = pd.concat(frames, ignore_index=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        r["rv100"] = 100 * r["rv"] / r["pitches"]
        r["woba"] = r["woba_num"] / r["woba_denom"]
        r["k_rate"] = r["k"] / r["pa"]
        r["bb_rate"] = r["bb"] / r["pa"]
        r["whiff"] = r["whiffs"] / r["swings"]
    return r


def load(cfg: dict) -> pd.DataFrame:
    t = pd.concat([pd.read_parquet(PROCESSED / f"monitor_{s}.parquet",
                                   columns=["pitcher", "season", "role", "game_pk", "game_date", "expected_velo", "velo_alarm"])
                   .assign(split=s) for s in ("dev", "val", "sealed")], ignore_index=True)
    o = pd.read_parquet(PROCESSED / "outings.parquet", columns=["pitcher", "season", "game_pk", "velo"])
    t = t.merge(o, on=["pitcher", "season", "game_pk"], how="left")
    t["gap"] = t["velo"] - t["expected_velo"]
    t["alarm"] = t["velo_alarm"].astype(float)
    t = t.merge(outing_results(cfg), on=["pitcher", "game_pk"], how="left")
    t["ps"] = t["pitcher"].astype(str) + "-" + t["season"].astype(str)
    # 같은 투수-시즌 안 다음 감시 등판의 결과(경보 다음 등판 분석용)
    t = t.sort_values(["ps", "game_date", "game_pk"]).reset_index(drop=True)
    for col in [*OUTCOMES, *set(OUTCOMES.values())]:
        t[f"next_{col}"] = t.groupby("ps")[col].shift(-1)
    return t


def main() -> None:
    cfg = load_config()
    t = load(cfg)
    print(f"감시 등판 {len(t)}, 결과를 못 붙인 등판 {int(t['pitches'].isna().sum())}, 구속 차이 없는 등판 {int(t['gap'].isna().sum())}")
    print("구속 차이(mph) 분포:", t["gap"].describe().round(2).to_dict())
    rows = []
    for name, d in (("all", t), ("val+sealed", t[t["split"] != "dev"])):
        for y, w in OUTCOMES.items():
            for exposure, x, yy, ww in (("per 1 mph below expectation", "gap", y, w), ("alarm outing vs other", "alarm", y, w),
                                        ("next outing after alarm vs other", "alarm", f"next_{y}", f"next_{w}")):
                r = mt.within_wls(d, yy, [x], group="ps", weight=ww, cluster="pitcher").loc[x]
                sign = -1 if x == "gap" else 1                    # 구속 차이는 '1 mph 느릴 때'로 뒤집어 보고
                lo, hi = sorted((sign * r["lo"], sign * r["hi"]))
                rows.append({"sample": name, "outcome": y, "exposure": exposure, "effect": sign * r["coef"], "lo": lo, "hi": hi,
                             "outings": int(r["n"]), "mean_outcome": np.average(d[y].dropna(), weights=d.loc[d[y].notna(), w])})
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "reports" / "tables" / "velocity_performance.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 250)
    print(out.to_string(index=False, float_format=lambda v: f"{v:.4g}"))


if __name__ == "__main__":
    main()
