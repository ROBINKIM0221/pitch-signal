"""사후 분석(사전 등록 아님): 구속 하락 경보 뒤 30일 안 팔 부상 IL 비율 차이에 대한 추론.

alarm_followup.py가 비율만 냈던 것을 두 가지로 보강한다.
1) 비율의 비(경보 ÷ 경보 없음)와, 투수를 통째로 다시 뽑는 부트스트랩 95% 구간 (분할별·합산)
2) 로지스틱 회귀: 역할·나이·그 시즌 앞선 투구 수·시즌을 보정한 오즈비, 표준오차는 투수로 묶음.
   경보(있음/없음)와 연속 지수(velo_index, 1이 경보선) 두 가지로.
결과는 reports/tables/alarm_il_inference.csv.

    python tools/alarm_il_inference.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))        # 저장소 어디서 실행해도 src를 찾게
from src.common import metrics as mt  # noqa: E402
from src.common.config import ROOT, load_config  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
DAYS = 30


def load(cfg: dict) -> pd.DataFrame:
    labels = pd.read_csv(PROCESSED / "labels.csv", encoding="utf-8-sig", parse_dates=["il_date"])
    labels = labels[labels["part"].isin(["elbow", "shoulder"])]
    frames = []
    for split in ("dev", "val", "sealed"):
        t = pd.read_parquet(PROCESSED / f"monitor_{split}.parquet",
                            columns=["pitcher", "season", "role", "game_pk", "game_date", "velo_alarm", "velo_index"])
        t["followed"] = mt.followed_within(t, labels[labels["season"].isin(cfg["data"]["split"][split])], DAYS)
        t["split"] = split
        frames.append(t)
    t = pd.concat(frames, ignore_index=True)
    # 보정 변수: 그 시즌 이 등판 전까지 던진 공 수(모든 등판 기준), 등판일 나이
    o = pd.read_parquet(PROCESSED / "outings.parquet", columns=["pitcher", "season", "game_pk", "game_date", "n_all"])
    o = o.sort_values(["pitcher", "season", "game_date", "game_pk"])
    o["prior_pitches"] = o.groupby(["pitcher", "season"])["n_all"].cumsum() - o["n_all"]
    t = t.merge(o[["pitcher", "season", "game_pk", "prior_pitches"]], on=["pitcher", "season", "game_pk"], how="left")
    people = pd.read_parquet(ROOT / "data" / "raw" / "people.parquet", columns=["id", "birth_date"])
    t = t.merge(people.rename(columns={"id": "pitcher"}), on="pitcher", how="left")
    t["age"] = (t["game_date"] - pd.to_datetime(t["birth_date"])).dt.days / 365.25
    t["log_prior"] = np.log1p(t["prior_pitches"])
    t["alarm"] = t["velo_alarm"].astype(int)
    t["y"] = t["followed"].astype(int)
    return t


def crude(t: pd.DataFrame, name: str, cfg: dict) -> dict:
    flag, fol = t["velo_alarm"].to_numpy(bool), t["followed"].to_numpy(bool)
    rr = mt.cluster_risk_ratio(fol, flag, t["pitcher"].to_numpy(), n_boot=cfg["evaluation"]["bootstrap_reps"], seed=cfg["seed"])
    return {"analysis": "crude risk ratio (pitcher bootstrap)", "sample": name, "outings": len(t), "pitchers": t["pitcher"].nunique(),
            "alarms": int(flag.sum()), "alarm_followed": int(fol[flag].sum()), "alarm_rate": fol[flag].mean(),
            "other_followed": int(fol[~flag].sum()), "other_rate": fol[~flag].mean(),
            "estimate": rr["rr"], "lo": rr["rr_lo"], "hi": rr["rr_hi"]}


def adjusted(t: pd.DataFrame, term: str, name: str) -> dict:
    d = t.dropna(subset=["age", "log_prior"])
    fit = smf.glm(f"y ~ {term} + C(role) + age + log_prior + C(season)", data=d, family=sm.families.Binomial()).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(d["pitcher"])[0]})
    lo, hi = fit.conf_int().loc[term]
    label = "adjusted odds ratio, alarm vs none" if term == "alarm" else "adjusted odds ratio per 1 unit of velocity-drop index"
    return {"analysis": label, "sample": name, "outings": len(d), "pitchers": d["pitcher"].nunique(),
            "estimate": float(np.exp(fit.params[term])), "lo": float(np.exp(lo)), "hi": float(np.exp(hi)), "p": float(fit.pvalues[term])}


def main() -> None:
    cfg = load_config()
    t = load(cfg)
    held_out = t[t["split"] != "dev"]                        # 신호 설계에 쓰지 않은 2024~2026
    rows = [crude(t[t["split"] == s], s, cfg) for s in ("dev", "val", "sealed")]
    rows += [crude(held_out, "val+sealed", cfg), crude(t, "all", cfg)]
    rows += [adjusted(d, term, name) for name, d in (("val+sealed", held_out), ("all", t)) for term in ("alarm", "velo_index")]
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "reports" / "tables" / "alarm_il_inference.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 250)
    print(f"나이·앞선 투구 수가 빠진 등판: {int(t[['age', 'log_prior']].isna().any(axis=1).sum())}")
    print(out.drop(columns="analysis").to_string(index=False, float_format=lambda v: f"{v:.3g}"))


if __name__ == "__main__":
    main()
