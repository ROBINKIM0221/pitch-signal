"""감시 엔진 (단계 4). 규칙은 docs/SPEC.md 3.7~3.9절. 개발셋(config.data.split.dev)만 처리한다.

사용 예:
    python -m src.06_monitor --baselines     # 4.1 평소가 움직이는 크기(합동 추정)와 투수-시즌별 시작 구간
    python -m src.06_monitor --theory-h      # 4.4 이론 관리한계 표와 설계 성능표
    python -m src.06_monitor --run           # 4.2 시작 구간 뒤 등판에 T²·MEWMA 적용 (이론 한계)
    python -m src.06_monitor --calib-plot    # 4.3 개발셋 대조군의 투구 수 보정 그래프 (고정 기준선과 비교)
    python -m src.06_monitor --calibrate     # 4.5 두 신호의 실측 보정(역할별)과 개발셋 지표 → config_calibrated.yaml
"""
from __future__ import annotations

import argparse
import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.common import baseline_window as bw
from src.common import calibration as cal
from src.common import metrics as mt
from src.common import monitoring as mon
from src.common import plots
from src.common.config import ROOT, load_config, save_calibrated
from src.core import stats_core as sc

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
ROLES = ("SP", "RP")
log = logging.getLogger("pitchsignal.monitor")


def lambdas(cfg: dict) -> list[float]:
    """고정값 λ와 민감도 분석용 λ."""
    return [cfg["monitor"]["lam"], *cfg["monitor"]["sensitivity_lambdas"]]


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
        for lam in lambdas(cfg):
            h = sc.calibrate_h(p, lam, ucl, target=m["arl0_target"], seed=m["calib"]["seed"], **sim)
            limits.append({"p": p, "lambda": lam, "t2_ucl": ucl, "h": h})
            for shift in m["design_shifts_sd"]:
                moved = np.zeros(p)
                moved[0] = shift
                design.append({"p": p, "lambda": lam, "shift_sd": shift, "arl1": sc.arl1(h, p, lam, ucl, moved, **sim)})
    limits = pd.DataFrame(limits)
    limits.to_csv(TABLES / "h_theory.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(design).to_csv(TABLES / "arl1_design.csv", index=False, encoding="utf-8-sig")
    k = pd.DataFrame({"lambda": lambdas(cfg), "k": [cal.theory_k(lam, m["arl0_target"], seed=m["calib"]["seed"], **sim)
                                                   for lam in lambdas(cfg)]})
    k.to_csv(TABLES / "k_theory.csv", index=False, encoding="utf-8-sig")        # 구속 하락 신호(한 방향 EWMA)의 이론 한계
    return limits


def run(cfg: dict) -> None:
    """개발셋의 시작 구간 뒤 적격 등판에 이론 한계로 T²·MEWMA를 적용해 monitor_dev.parquet로 저장한다."""
    core, m, rules = cfg["features"]["core"], cfg["monitor"], cfg["baseline"]
    table = mon.dynamic_table(dev_outings(cfg), pd.read_parquet(PROCESSED / "baselines.parquet"),
                              dynamics_from_config(cfg), rules, core, sc.t2_ucl(len(core), rules["refine_alpha"]))
    path = TABLES / "h_theory.csv"
    limits = pd.read_csv(path, encoding="utf-8-sig") if path.exists() else theory(cfg)
    limits = limits[limits["p"] == len(core)].set_index("lambda")
    table = mon.run_charts(table, core, {lam: (limits.loc[lam, "h"], limits.loc[lam, "t2_ucl"]) for lam in lambdas(cfg)},
                           m["reset_after_alarm"])
    table.to_parquet(PROCESSED / "monitor_dev.parquet", compression="zstd", index=False)

    log.info("감시 등판 %d개 (투수-시즌 %d개) 저장. 이론 한계: %s", len(table),
             table.groupby(["pitcher", "season"]).ngroups, limits["h"].round(2).to_dict())
    print("투구 수 구간별 u 분산과 T² 평균 — 감시 등판 전체 기준 (대조군 기준 표는 단계 4.3)")
    for role in ROLES:
        print(role)
        print(mon.calibration_by_n(table[table["role"] == role], core, m["calibration_plot"]["n_bins"])
              .to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    alarms = table.groupby("role")[[f"alarm_{lam}" for lam in lambdas(cfg)]].mean() * 100
    print("이론 한계에서 100등판당 경보 수 — 감시 등판 전체 기준")
    print(alarms.to_string(float_format=lambda v: f"{v:.2f}"))
    print("T²만으로 100등판당:", (table.groupby("role")["t2"].apply(
        lambda t: 100 * (t > limits["t2_ucl"].iloc[0]).mean())).round(2).to_dict())


def dev_controls(cfg: dict) -> pd.DataFrame:
    controls = pd.read_csv(PROCESSED / "controls.csv", encoding="utf-8-sig")
    return controls[controls["season"].isin(cfg["data"]["split"]["dev"])]


def control_rows(table: pd.DataFrame, controls: pd.DataFrame) -> np.ndarray:
    """표의 줄 가운데 대조군 투수-시즌의 것."""
    return pd.MultiIndex.from_frame(table[["pitcher", "season"]]).isin(pd.MultiIndex.from_frame(controls[["pitcher", "season"]]))


def calib_plot(cfg: dict) -> None:
    """투구 수 보정 그래프 (단계 4.3). 개발셋 대조군 감시 등판에서 구간별 u 분산을 보고, 고정 기준선(비교용)과 견준다.

    결과: reports/tables/calib_by_n.csv, calib_by_order.csv, reports/figures/calib_by_n.png.
    평가 계획서 4.1 규칙: 대조군 등판이 min_bin_outings개 이상인 구간 중 분산이 var_limit를 넘는 곳이 있으면 하한을 올린다.
    """
    core, cp, rules = cfg["features"]["core"], cfg["monitor"]["calibration_plot"], cfg["baseline"]
    controls = dev_controls(cfg)
    moving = pd.read_parquet(PROCESSED / "monitor_dev.parquet").sort_values(bw.ORDER)
    moving = moving[control_rows(moving, controls)]
    outings = dev_outings(cfg)
    outings = outings[control_rows(outings, controls)]
    pitches_fb = pd.read_parquet(PROCESSED / "pitches_fb.parquet")
    pitches_fb = pitches_fb[control_rows(pitches_fb, controls)]
    fixed = mon.fixed_table(outings, mon.outing_arrays(pitches_fb, core), pd.read_parquet(PROCESSED / "baselines.parquet"),
                            rules, core)

    by_n, by_order = [], []
    for name, table in (("moving", moving), ("fixed", fixed)):
        for role in ROLES:
            part = table[table["role"] == role]
            by_n.append(mon.calibration_by_n(part, core, cp["n_bins"]).assign(role=role, baseline=name))
            by_order.append(mon.calibration_by_order(part, core, cp["order_bins"]).assign(role=role, baseline=name))
    by_n, by_order = pd.concat(by_n, ignore_index=True), pd.concat(by_order, ignore_index=True)
    by_n.to_csv(TABLES / "calib_by_n.csv", index=False, encoding="utf-8-sig")
    by_order.to_csv(TABLES / "calib_by_order.csv", index=False, encoding="utf-8-sig")

    labels = {"velo": "구속", "rel_z": "수직 릴리스", "arm_angle": "팔 각도"}
    colors = {"velo": plots.SERIES, "rel_z": "#d9822b", "arm_angle": "#3f9b6c"}
    plots.use_style()
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.2))
    for row, role in enumerate(ROLES):
        ax = axes[row, 0]
        part = by_n[(by_n["role"] == role) & (by_n["baseline"] == "moving")]
        x = np.arange(len(part))
        for j, f in enumerate(core):
            ax.bar(x + (j - 1) * 0.26, part[f"var_u_{f}"], width=0.24, color=colors[f], label=labels[f])
        for i, n in enumerate(part["outings"]):
            ax.text(x[i], 0.04, f"{n:,}", ha="center", va="bottom", color=plots.INK_SECONDARY, fontsize=8)
        ax.axhline(1.0, color=plots.MUTED, linewidth=0.8)
        ax.axhline(cp["var_limit"], color=plots.MUTED, linewidth=0.8, linestyle="--")
        ax.set_xticks(x, part["n_fb_bin"])
        ax.set_ylim(0, max(1.6, float(part[[f"var_u_{f}" for f in core]].max().max()) + 0.15))
        ax.set_title(f"{'선발' if role == 'SP' else '불펜'} 대조군: 주력 패스트볼 수 구간별 u 분산 (움직이는 기준선)")
        ax.set_xlabel("등판의 주력 패스트볼 수 (막대 아래 숫자는 등판 수)")
        ax.set_ylabel("u 분산 (정상이면 1, 점선은 한계 1.3)")
        if row == 0:
            ax.legend(frameon=False, ncol=3, loc="upper right")

        ax = axes[row, 1]
        for name, color, label in (("moving", plots.SERIES, "움직이는 기준선"), ("fixed", plots.MUTED, "고정 기준선 (비교용)")):
            part = by_order[(by_order["role"] == role) & (by_order["baseline"] == name)]
            ax.plot(part["order_bin"], part[[f"var_u_{f}" for f in core]].mean(axis=1), marker="o", color=color, label=label)
        ax.axhline(1.0, color=plots.MUTED, linewidth=0.8)
        ax.set_title(f"{'선발' if role == 'SP' else '불펜'} 대조군: 시작 구간 뒤 등판 순서별 u 분산 (세 특징 평균)")
        ax.set_xlabel("시작 구간 뒤 몇 번째 감시 등판인지")
        ax.set_ylabel("u 분산")
        if row == 0:
            ax.legend(frameon=False, loc="upper left")
    dev = cfg["data"]["split"]["dev"]
    fig.suptitle(f"표준화 점검, 개발셋 {dev[0]}~{dev[-1]} 대조군 {controls.groupby(['pitcher', 'season']).ngroups}명", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(ROOT / "reports" / "figures" / "calib_by_n.png")

    flagged = []
    for role in ROLES:
        part = by_n[(by_n["role"] == role) & (by_n["baseline"] == "moving")]
        flagged += [(role, *hit) for hit in mon.over_limit(part, core, cp["var_limit"], cp["min_bin_outings"])]
    log.info("보정 그래프 저장. 등판 %d개 이상 구간 중 분산 %.1f 초과: %s", cp["min_bin_outings"], cp["var_limit"], flagged or "없음")
    print(by_n[by_n["baseline"] == "moving"].to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    print("\n고정 기준선과 비교 (등판 순서별, 세 특징 평균 분산)")
    wide = by_order.assign(var=by_order[[f"var_u_{f}" for f in core]].mean(axis=1)).pivot_table(
        index=["role", "order_bin"], columns="baseline", values="var", sort=False)
    print(wide.to_string(float_format=lambda v: f"{v:.2f}"))
    thin = by_n[(by_n["baseline"] == "moving") & (by_n["outings"] < cp["min_bin_outings"])]
    if len(thin):
        print("\n등판이 적어 판정에서 뺀 구간:", [(r, b, int(n)) for r, b, n in zip(thin["role"], thin["n_fb_bin"], thin["outings"])])
    print("규칙에 걸린 구간:", flagged or "없음 → 하한 유지")


def calibrate(cfg: dict) -> None:
    """두 신호의 실측 보정 (단계 4.5). 개발셋 대조군만으로 역할별 한계를 맞추고, 개발셋 사례로 지표를 낸다.

    결과: config_calibrated.yaml의 monitor.final, reports/tables/calibration_dev.csv,
          monitor_dev.parquet에 두 신호의 경보·지수 열 추가. 검증셋은 쓰지 않는다.
    """
    core, m, dev = cfg["features"]["core"], cfg["monitor"], cfg["data"]["split"]["dev"]
    lam, target, reps = m["lam"], 100 / m["arl0_target"], cfg["evaluation"]["bootstrap_reps"]
    table = pd.read_parquet(PROCESSED / "monitor_dev.parquet").sort_values(bw.ORDER).reset_index(drop=True)
    controls = pd.read_csv(PROCESSED / "controls.csv", encoding="utf-8-sig")
    controls = controls[controls["season"].isin(dev)]
    cases = pd.read_csv(PROCESSED / "cases.csv", encoding="utf-8-sig")
    windows = pd.read_csv(PROCESSED / "windows.csv", encoding="utf-8-sig")
    windows = windows[windows["season"].isin(dev)]
    is_control = pd.MultiIndex.from_frame(table[["pitcher", "season"]]).isin(
        pd.MultiIndex.from_frame(controls[["pitcher", "season"]]))
    k_theory = pd.read_csv(TABLES / "k_theory.csv", encoding="utf-8-sig").set_index("lambda")["k"]
    h_theory = pd.read_csv(TABLES / "h_theory.csv", encoding="utf-8-sig")
    h_theory = h_theory[h_theory["p"] == len(core)].set_index("lambda")["h"]
    t2_start = sc.t2_ucl(len(core), m["t2_alpha"])

    rules, rows = {}, []
    for role in ROLES:
        ctl = table[is_control & (table["role"] == role).to_numpy()]
        seqs = cal.sequences(ctl, core)
        t2 = cal.t2_limit(ctl["t2"].to_numpy(), t2_start, m["t2_max_far_per100"])
        velo = cal.fit_velo([uv for _, uv in seqs], lam, target)
        change = cal.fit_change([u for u, _ in seqs], lam, t2, target)
        rules[role] = (velo, change)
        rows.append({"role": role, "control_outings": len(ctl), "k_theory": k_theory[lam], "k": velo.k,
                     "t2_theory": t2_start, "t2": t2, "h_theory": h_theory[lam], "h": change.h})
    table = cal.table_signals(table, core, rules)
    table.to_parquet(PROCESSED / "monitor_dev.parquet", compression="zstd", index=False)

    summary = pd.DataFrame(rows).set_index("role")
    for signal in ("velo", "change"):
        alarm, index = f"{signal}_alarm", f"{signal}_index"
        results = mt.window_results(windows, table, alarm=alarm, index=index).merge(cases[["case_id", "role"]], on="case_id")
        for role, sel, part in [(r, is_control & (table["role"] == r).to_numpy(), results[results["role"] == r]) for r in ROLES] + \
                               [("all", is_control, results)]:
            d = mt.detection(part)
            mean, lo, hi = mt.bootstrap_ci(mt.concordance(part), reps, cfg["seed"])
            summary.loc[role, f"{signal}_far"] = 100 * table.loc[sel, alarm].mean()
            summary.loc[role, f"{signal}_detection"] = 100 * d["detection_rate"]
            summary.loc[role, f"{signal}_control_window"] = 100 * d["control_window_rate"]
            summary.loc[role, f"{signal}_median_lead"] = d["median_lead"]
            summary.loc[role, f"{signal}_concordance"] = mean
            summary.loc[role, f"{signal}_concordance_lo"], summary.loc[role, f"{signal}_concordance_hi"] = lo, hi
    summary.to_csv(TABLES / "calibration_dev.csv", encoding="utf-8-sig")
    save_calibrated({"monitor": {"final": {
        "lam": lam, "velo": {role: {"k": round(float(rules[role][0].k), 4)} for role in ROLES},
        "change": {role: {"t2": round(float(rules[role][1].t2), 4), "h": round(float(rules[role][1].h), 4)} for role in ROLES}}}})

    log.info("실측 보정 완료 (λ = %s, 신호마다 역할별 100등판당 %.1f). 결과 → %s", lam, target, TABLES / "calibration_dev.csv")
    print(summary.T.to_string(float_format=lambda v: f"{v:.3f}"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baselines", action="store_true", help="평소가 움직이는 크기의 합동 추정과 투수-시즌별 시작 구간 (단계 4.1)")
    ap.add_argument("--theory-h", action="store_true", help="이론 관리한계 표와 설계 성능표 (단계 4.4)")
    ap.add_argument("--run", action="store_true", help="시작 구간 뒤 등판에 T²·MEWMA 적용 (단계 4.2)")
    ap.add_argument("--calib-plot", action="store_true", help="개발셋 대조군의 투구 수 보정 그래프 (단계 4.3)")
    ap.add_argument("--calibrate", action="store_true", help="두 신호의 실측 보정과 개발셋 지표 (단계 4.5)")
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
    elif a.calib_plot:
        calib_plot(cfg)
    elif a.calibrate:
        calibrate(cfg)
    else:
        ap.error("할 일을 골라 주세요 (--baselines, --theory-h, --run, --calib-plot, --calibrate)")


if __name__ == "__main__":
    main()
