"""비교 대상 B1~B4의 개발셋 맞춤 (단계 5.1). 규칙은 docs/SPEC.md 3.12절. 검증셋은 쓰지 않는다.

B2·B3·B4의 임계값을 개발셋 대조군 실측 오경보율이 신호와 같은 기준(100등판당 1.0, 선발·불펜 따로)이 되게 찾아
config_calibrated.yaml의 comparators에 쓰고, B1은 고정 임계의 실측 오경보율을 그대로 기록한다.
개발셋 지표(탐지율, 대조군 창 내 경보, 창 지수 일치도)를 reports/tables/comparators_dev.csv에 저장하고,
monitor_dev.parquet에 비교 대상의 경보·지수 열(b1_~b4_)을 붙인다.

사용 예:
    python -m src.07_comparators
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from src.common import baseline_window as bw
from src.common import calibration as cal
from src.common import comparators as cp
from src.common import metrics as mt
from src.common.config import ROOT, load_config, save_calibrated

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
ROLES = ("SP", "RP")
NAMES = {"b1": "B1", "b2": "B2", "b3": "B3", "b4": "B4"}
log = logging.getLogger("pitchsignal.comparators")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "comparators.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    core, m, dev = cfg["features"]["core"], cfg["monitor"], cfg["data"]["split"]["dev"]
    lam, target, reps = m["lam"], 100 / m["arl0_target"], cfg["evaluation"]["bootstrap_reps"]

    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    outings = outings[outings["season"].isin(dev)].copy()
    outings["phase"] = bw.phase(outings, cfg["baseline"]).to_numpy()
    monitor = pd.read_parquet(PROCESSED / "monitor_dev.parquet").sort_values(bw.ORDER).reset_index(drop=True)
    controls = pd.read_csv(PROCESSED / "controls.csv", encoding="utf-8-sig")
    controls = controls[controls["season"].isin(dev)]
    cases = pd.read_csv(PROCESSED / "cases.csv", encoding="utf-8-sig")
    windows = pd.read_csv(PROCESSED / "windows.csv", encoding="utf-8-sig")
    windows = windows[windows["season"].isin(dev)]

    whip_cap = float(np.nanpercentile(cp.whip(outings, cfg["B2"]["ip_floor_outs"], np.inf), cfg["B2"]["winsor_pct"]))
    stats = cp.statistics(outings, monitor[[*cp.OUTING, "uv", *[f"sd_{f}" for f in core]]], core, cfg, whip_cap)
    is_control = pd.MultiIndex.from_frame(stats[["pitcher", "season"]]).isin(pd.MultiIndex.from_frame(controls[["pitcher", "season"]]))

    limits = {"B2": {}, "B3": {}, "B4": {}}
    for role in ROLES:
        ctl = stats[is_control & (stats["role"] == role).to_numpy()]
        groups = [g for _, g in ctl.groupby(["pitcher", "season"], sort=False)]
        limits["B2"][role] = cp.threshold_for_rate(
            lambda h: [cp.b2_cusum(g["b2_w"].to_numpy(dtype=float), cfg["B2"]["cusum_k"], h)[0] for g in groups], target)
        limits["B3"][role] = cal.t2_limit(ctl["b3_d2"].dropna().to_numpy(), 0.0, target)
        limits["B4"][role] = cp.threshold_for_rate(lambda h: [cp.b4_ewma(g["uv"].to_numpy(dtype=float), h, lam)[0] for g in groups], target)
    table = cp.alarms(stats, limits, cfg, lam)

    rows = []
    for key, name in NAMES.items():
        results = mt.window_results(windows, table, alarm=f"{key}_alarm", index=f"{key}_index").merge(cases[["case_id", "role"]], on="case_id")
        for role in (*ROLES, "all"):
            sel = is_control if role == "all" else is_control & (table["role"] == role).to_numpy()
            part = results if role == "all" else results[results["role"] == role]
            d = mt.detection(part)
            mean, lo, hi = mt.bootstrap_ci(mt.concordance(part), reps, cfg["seed"])
            rows.append({"method": name, "role": role,
                         "threshold": cfg["B1"]["velo_drop_mph"] if name == "B1" else (limits[name][role] if role != "all" else np.nan),
                         "control_far": 100 * table.loc[sel, f"{key}_alarm"].mean(), "detection": 100 * d["detection_rate"],
                         "control_window": 100 * d["control_window_rate"], "median_lead": d["median_lead"],
                         "concordance": mean, "concordance_lo": lo, "concordance_hi": hi})
    summary = pd.DataFrame(rows)
    summary.to_csv(TABLES / "comparators_dev.csv", index=False, encoding="utf-8-sig")
    save_calibrated({"comparators": {
        "B2": {"whip_cap": round(whip_cap, 4), **{r: {"h": round(float(limits["B2"][r]), 4)} for r in ROLES}},
        "B3": {r: {"d2": round(float(limits["B3"][r]), 4)} for r in ROLES},
        "B4": {r: {"h": round(float(limits["B4"][r]), 4)} for r in ROLES}}})

    columns = [c for c in table.columns if c[:2] in NAMES and c[2] == "_"]
    merged = monitor.drop(columns=[c for c in monitor.columns if c in columns]).merge(table[[*cp.OUTING, *columns]], on=cp.OUTING, how="left")
    merged.to_parquet(PROCESSED / "monitor_dev.parquet", compression="zstd", index=False)

    log.info("비교 대상 맞춤 완료 (WHIP 상한 %.2f). 임계값: %s", whip_cap, {k: {r: round(v, 3) for r, v in d.items()} for k, d in limits.items()})
    pd.set_option("display.width", 220)
    print(summary.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


if __name__ == "__main__":
    main()
