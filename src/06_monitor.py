"""감시 엔진 (단계 4). 규칙은 docs/SPEC.md 3.7~3.9절. 개발셋(config.data.split.dev)만 처리한다.

사용 예:
    python -m src.06_monitor --baselines     # 4.1 평소가 움직이는 크기(합동 추정)와 투수-시즌별 시작 구간
    python -m src.06_monitor --theory-h      # 4.4 이론 관리한계 표와 설계 성능표
    python -m src.06_monitor --run           # 4.2 시작 구간 뒤 등판에 T²·MEWMA 적용 (이론 한계)
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd

from src.common import baseline_window as bw
from src.common import monitoring as mon
from src.common.config import ROOT, load_config, save_calibrated
from src.core import stats_core as sc

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
ROLES = ("SP", "RP")
log = logging.getLogger("pitchsignal.monitor")


def dev_outings(cfg: dict) -> pd.DataFrame:
    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    return outings[outings["season"].isin(cfg["data"]["split"]["dev"])]


def dynamics_from_config(cfg: dict) -> dict:
    saved = cfg["baseline"]["dynamics"]
    return {role: mon.Dynamics(Q=np.array(saved[role]["Q"]), Se=np.array(saved[role]["Se"])) for role in ROLES}


def baselines(cfg: dict) -> None:
    """개발셋에서 역할별로 평소가 움직이는 크기(Q)와 등판마다 흔들리는 크기(Σ_e)를 합동 추정하고,
    투수-시즌별 시작 구간 값(단위를 없애는 값, 본인의 Σ_w)을 저장한다. 비교용 고정 기준선도 함께 만든다."""
    core, rules = cfg["features"]["core"], cfg["baseline"]
    outings = dev_outings(cfg)
    pitches_fb = pd.read_parquet(PROCESSED / "pitches_fb.parquet")
    arrays = mon.outing_arrays(pitches_fb[pitches_fb["season"].isin(cfg["data"]["split"]["dev"])], core)
    windows = bw.baseline_windows(outings, rules)
    have = windows[windows["n_baseline"] > 0]
    phased = outings.assign(phase=bw.phase(outings, rules).to_numpy())
    eligible = {key: g for key, g in phased[phased["phase"] != ""].sort_values(bw.ORDER).groupby(["pitcher", "season"])}

    started, seasons, unitless = {}, {role: [] for role in ROLES}, {role: [] for role in ROLES}
    for w in have.itertuples():
        base = [arrays[(w.pitcher, w.season, game)] for game in w.baseline_games]
        scale, sw = mon.start_up(base)
        started[(w.pitcher, w.season)] = (base, scale, sw)
        g = eligible[(w.pitcher, w.season)]
        seasons[w.role].append((g[core].to_numpy(dtype=float) / scale, g["n_fb"].to_numpy(dtype=float), sw))
        unitless[w.role].append([o / scale for o in base])

    def as_lists(role):
        d = mon.pooled_dynamics(seasons[role], rules["level_step_eigen_floor"], rules["sb_eigen_floor"])
        return {"Q": d.Q.round(6).tolist(), "Se": d.Se.round(6).tolist()}

    save_calibrated({"baseline": {
        "dynamics": {"features": core, **{role: as_lists(role) for role in ROLES}},
        "fixed_sigma_b": {"features": core, **{role: mon.pooled_sigma_b(unitless[role], rules["sb_eigen_floor"])
                                              .round(6).tolist() for role in ROLES}}}})
    saved = load_config()["baseline"]

    ucl = sc.t2_ucl(len(core), rules["refine_alpha"])
    rows = []
    for w in have.itertuples():
        base, scale, sw = started[(w.pitcher, w.season)]
        _, fixed, removed = mon.fit_baseline(base, np.array(saved["fixed_sigma_b"][w.role]), ucl)
        rows.append({"pitcher": w.pitcher, "season": w.season, "role": w.role, "baseline_end": w.baseline_end,
                     "n_baseline": w.n_baseline, "scale": scale.tolist(), "Sw": sw.ravel().tolist(),
                     "fixed_mu": fixed.mu.tolist(), "fixed_Sb": fixed.Sb.ravel().tolist(),
                     "fixed_Sw": fixed.Sw.ravel().tolist(), "fixed_removed": len(removed)})
    fits = pd.DataFrame(rows)
    fits.to_parquet(PROCESSED / "baselines.parquet", compression="zstd", index=False)

    for role in ROLES:
        log.info("%s (%s): 평소가 한 등판 사이에 움직이는 표준편차 %s, 등판마다 흔들리는 표준편차 %s (등판 안 표준편차 = 1)",
                 role, core, np.sqrt(np.diag(saved["dynamics"][role]["Q"])).round(3).tolist(),
                 np.sqrt(np.diag(saved["dynamics"][role]["Se"])).round(3).tolist())
    summary = pd.DataFrame({
        "pitcher_seasons": windows.groupby("role").size(),
        "with_baseline": have.groupby("role").size(),
        "without_baseline": windows[windows["n_baseline"] == 0].groupby("role").size(),
        "outings_for_dynamics": {role: sum(len(s[1]) for s in seasons[role]) for role in ROLES},
    }).reindex(list(ROLES))
    summary.to_csv(TABLES / "baselines_dev.csv", encoding="utf-8-sig")
    print(summary.T.to_string())
    print("시작 구간이 없는 이유: 선발은 적격 등판 "
          f"{rules['starter_outings']}개 미만, 불펜은 {rules['reliever_outings']}개 미만이거나 주력 패스트볼 누적 "
          f"{rules['reliever_min_fastballs']}구 미만")


def theory(cfg: dict) -> pd.DataFrame:
    """표준정규 시퀀스로 이론 관리한계 h(ARL0 = 목표값)와 설계 성능표(ARL1)를 계산해 저장한다."""
    m = cfg["monitor"]
    sim = {"n_sim": m["calib"]["n_sim"], "max_len": m["calib"]["max_len"]}
    limits, design = [], []
    for p in m["theory_feature_counts"]:
        ucl = sc.t2_ucl(p, m["t2_alpha"])
        for lam in m["lambdas"]:
            h = sc.calibrate_h(p, lam, ucl, target=m["arl0_target"], seed=m["calib"]["seed"], **sim)
            limits.append({"p": p, "lambda": lam, "t2_ucl": ucl, "h": h})
            for shift in m["design_shifts_sd"]:
                moved = np.zeros(p)
                moved[0] = shift
                design.append({"p": p, "lambda": lam, "shift_sd": shift, "arl1": sc.arl1(h, p, lam, ucl, moved, **sim)})
    limits = pd.DataFrame(limits)
    limits.to_csv(TABLES / "h_theory.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(design).to_csv(TABLES / "arl1_design.csv", index=False, encoding="utf-8-sig")
    return limits


def run(cfg: dict) -> None:
    """개발셋의 시작 구간 뒤 적격 등판에 이론 한계로 T²·MEWMA를 적용해 monitor_dev.parquet로 저장한다."""
    core, m, rules = cfg["features"]["core"], cfg["monitor"], cfg["baseline"]
    table = mon.dynamic_table(dev_outings(cfg), pd.read_parquet(PROCESSED / "baselines.parquet"),
                              dynamics_from_config(cfg), rules, core, sc.t2_ucl(len(core), rules["refine_alpha"]))
    path = TABLES / "h_theory.csv"
    limits = pd.read_csv(path, encoding="utf-8-sig") if path.exists() else theory(cfg)
    limits = limits[limits["p"] == len(core)].set_index("lambda")
    table = mon.run_charts(table, core, {lam: (limits.loc[lam, "h"], limits.loc[lam, "t2_ucl"]) for lam in m["lambdas"]},
                           m["reset_after_alarm"])
    table.to_parquet(PROCESSED / "monitor_dev.parquet", compression="zstd", index=False)

    log.info("감시 등판 %d개 (투수-시즌 %d개) 저장. 이론 한계: %s", len(table),
             table.groupby(["pitcher", "season"]).ngroups, limits["h"].round(2).to_dict())
    print("투구 수 구간별 u 분산과 T² 평균 — 감시 등판 전체 기준 (대조군 기준 표는 단계 4.3)")
    for role in ROLES:
        print(role)
        print(mon.calibration_by_n(table[table["role"] == role], core, m["calibration_plot"]["n_bins"])
              .to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    alarms = table.groupby("role")[[f"alarm_{lam}" for lam in m["lambdas"]]].mean() * 100
    print("이론 한계에서 100등판당 경보 수 — 감시 등판 전체 기준")
    print(alarms.to_string(float_format=lambda v: f"{v:.2f}"))
    print("T²만으로 100등판당:", (table.groupby("role")["t2"].apply(
        lambda t: 100 * (t > limits["t2_ucl"].iloc[0]).mean())).round(2).to_dict())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baselines", action="store_true", help="평소가 움직이는 크기의 합동 추정과 투수-시즌별 시작 구간 (단계 4.1)")
    ap.add_argument("--theory-h", action="store_true", help="이론 관리한계 표와 설계 성능표 (단계 4.4)")
    ap.add_argument("--run", action="store_true", help="시작 구간 뒤 등판에 T²·MEWMA 적용 (단계 4.2)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "monitor.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    if a.baselines:
        baselines(cfg)
    elif a.theory_h:
        print(theory(cfg).pivot(index="p", columns="lambda", values="h").round(2).to_string())
    elif a.run:
        run(cfg)
    else:
        ap.error("할 일을 골라 주세요 (--baselines, --theory-h, --run)")


if __name__ == "__main__":
    main()
