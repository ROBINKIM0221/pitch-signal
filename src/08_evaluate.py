"""분할 평가 (단계 5.2~5.3). 규칙은 docs/SPEC.md 3.13절. 개발셋으로 시험하고, 검증셋은 평가 계획 고정 뒤에 한 번 돌린다.

    python -m src.08_evaluate --split dev
    python -m src.08_evaluate --split val      # docs/eval_plan.md가 FROZEN: true 일 때만
    python -m src.08_evaluate --split dev --h4 # H4: 불펜 사례·대조군의 관찰 창 기간 부하 표시 (단계 5.5)
2026 봉인 평가는 09_sealed로만 실행한다.

결과 (reports/tables): <split>_results.csv(방법별 지표), <split>_false_alarms.csv(역할·시즌별 오경보),
<split>_tests.csv(가설 판정과 McNemar·Holm), <split>_opcurve.csv와 reports/figures/<split>_opcurve.png(운영 곡선).
대시보드용: data/processed/monitor_<split>.parquet, alerts_<split>.parquet.
"""
from __future__ import annotations

import argparse
import logging

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.common import calibration as cal
from src.common import comparators as cp
from src.common import metrics as mt
from src.common import myt
from src.common import pipeline
from src.common import plots
from src.common.config import ROOT, load_config

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
METHODS = {"velo": "구속 하락 신호", "change": "폼 변화 신호", "b1": "B1 구속 1mph", "b2": "B2 WHIP CUSUM",
           "b3": "B3 마할라노비스", "b4": "B4 구속 EWMA(양방향)", "consensus": "합의 규칙"}
COMPARED = ["b1", "b2", "b3", "b4"]
log = logging.getLogger("pitchsignal.evaluate")


def frozen() -> bool:
    return (ROOT / "docs" / "eval_plan.md").read_text(encoding="utf-8").splitlines()[0].strip() == "FROZEN: true"


def split_data(cfg: dict, split: str):
    seasons = cfg["data"]["split"][split]
    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    pitches_fb = pd.read_parquet(PROCESSED / "pitches_fb.parquet")
    cases = pd.read_csv(PROCESSED / "cases.csv", encoding="utf-8-sig")
    controls = pd.read_csv(PROCESSED / "controls.csv", encoding="utf-8-sig")
    windows = pd.read_csv(PROCESSED / "windows.csv", encoding="utf-8-sig")
    pick = lambda d: d[d["season"].isin(seasons)]      # noqa: E731
    return pick(outings), pick(pitches_fb), pick(cases), pick(controls), pick(windows)


def add_consensus(table: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """합의 규칙(탐색): 구성원 중 min_methods개 이상이 같은 등판에서 경보. 지수는 경보 수 ÷ 필요한 수."""
    members = {"PROPOSED": "velo_alarm", "B1": "b1_alarm", "B2": "b2_alarm", "B3": "b3_alarm", "B4": "b4_alarm"}
    c = cfg["evaluation"]["consensus"]
    votes = table[[members[m] for m in c["members"]]].sum(axis=1)
    return table.assign(consensus_alarm=votes >= c["min_methods"], consensus_index=votes / c["min_methods"])


def scaled(table_in: pd.DataFrame, cfg: dict, outings: pd.DataFrame, scale: float) -> pd.DataFrame:
    """모든 한계에 scale을 곱했을 때의 경보 (운영 곡선용)."""
    core, lam = cfg["features"]["core"], cfg["monitor"]["lam"]
    rules = {role: (cal.VeloRule(lam, v.k * scale), cal.ChangeRule(lam, c.t2 * scale, c.h * scale))
             for role, (v, c) in cal.final_rules(cfg).items()}
    out = cal.table_signals(table_in, core, rules)
    limits = {name: {r: v * scale for r, v in d.items()} for name, d in pipeline.comparator_limits(cfg).items()}
    b1 = {**cfg, "B1": {"velo_drop_mph": cfg["B1"]["velo_drop_mph"] * scale}}
    stats = table_in[[*cp.OUTING, "role", "game_date", "uv", "b1_drop", "b2_w", "b3_d2"]]
    marked = cp.alarms(stats, limits, b1, lam)
    columns = [c for c in marked.columns if c.startswith("b") and c[1].isdigit() and c[2] == "_"]
    return out.drop(columns=columns).merge(marked[[*cp.OUTING, *columns]], on=cp.OUTING, how="left")


def evaluate(cfg: dict, split: str) -> None:
    outings, pitches_fb, cases, controls, windows = split_data(cfg, split)
    table = add_consensus(pipeline.monitor_table(cfg, outings, pitches_fb), cfg)
    is_control = pd.MultiIndex.from_frame(table[["pitcher", "season"]]).isin(pd.MultiIndex.from_frame(controls[["pitcher", "season"]]))
    reps, seed = cfg["evaluation"]["bootstrap_reps"], cfg["seed"]

    results, hits, far_tables = [], {}, []
    for key, name in METHODS.items():
        r = mt.window_results(windows, table, alarm=f"{key}_alarm", index=f"{key}_index").merge(cases[["case_id", "role", "part"]], on="case_id")
        hits[key] = r[r["group"] == "case"].set_index("case_id")["hit"]
        for group, part in (("all", r), ("SP", r[r["role"] == "SP"]), ("RP", r[r["role"] == "RP"]),
                            ("elbow", r[r["part"] == "elbow"]), ("shoulder", r[r["part"] == "shoulder"])):
            d = mt.detection(part)
            conc, lo, hi = mt.bootstrap_ci(mt.concordance(part), reps, seed)
            case_hit = part.loc[part["group"] == "case"].set_index("case_id")["hit"].astype(float)
            ctl_hit = part[part["group"] == "control"].groupby("case_id")["hit"].mean()
            diff, dlo, dhi = mt.bootstrap_ci((case_hit - ctl_hit).dropna(), reps, seed)
            sel = is_control if group == "all" else (is_control & (table["role"] == group).to_numpy() if group in ("SP", "RP") else None)
            results.append({"method": name, "group": group, "cases": d["cases"], "controls": d["controls"],
                            "concordance": conc, "concordance_lo": lo, "concordance_hi": hi,
                            "detection": 100 * d["detection_rate"], "control_window": 100 * d["control_window_rate"],
                            "diff": 100 * diff, "diff_lo": 100 * dlo, "diff_hi": 100 * dhi, "median_lead": d["median_lead"],
                            "false_alarms_per100": 100 * table.loc[sel, f"{key}_alarm"].mean() if sel is not None else np.nan})
        far_tables.append(mt.false_alarm_table(table[is_control], f"{key}_alarm").assign(method=name))
    results = pd.DataFrame(results)
    results.to_csv(TABLES / f"{split}_results.csv", index=False, encoding="utf-8-sig")
    pd.concat(far_tables, ignore_index=True).to_csv(TABLES / f"{split}_false_alarms.csv", index=False, encoding="utf-8-sig")

    # 가설 판정과 비교 검정
    velo = results[(results["method"] == METHODS["velo"]) & (results["group"] == "all")].iloc[0]
    tests = [{"test": "H1 구속 하락 지수 일치도 > 0.5", "value": velo["concordance"], "ci_lo": velo["concordance_lo"],
              "ci_hi": velo["concordance_hi"], "supported": bool(velo["concordance_lo"] > 0.5)},
             {"test": "H2 선행 등판 수 중앙값 ≥ 2 (구속 하락 신호)", "value": velo["median_lead"], "supported": bool(velo["median_lead"] >= 2)}]
    pvalues = [mt.mcnemar_exact(hits["velo"], hits[k].reindex(hits["velo"].index)) for k in COMPARED]
    for k, p, adj in zip(COMPARED, pvalues, mt.holm(pvalues)):
        tests.append({"test": f"McNemar 구속 하락 신호 vs {METHODS[k]}", "value": p, "holm": adj})
    pd.DataFrame(tests).to_csv(TABLES / f"{split}_tests.csv", index=False, encoding="utf-8-sig")

    # 운영 곡선
    points = []
    for s in cfg["evaluation"]["opcurve_scales"]:
        t = add_consensus(scaled(table, cfg, outings, s), cfg)
        for key, name in METHODS.items():
            r = mt.window_results(windows, t, alarm=f"{key}_alarm")
            d = mt.detection(r)
            points.append({"method": name, "scale": s, "false_alarms_per100": 100 * t.loc[is_control, f"{key}_alarm"].mean(),
                           "detection": 100 * d["detection_rate"], "control_window": 100 * d["control_window_rate"]})
    points = pd.DataFrame(points)
    points.to_csv(TABLES / f"{split}_opcurve.csv", index=False, encoding="utf-8-sig")
    draw_opcurve(points, split, cfg)

    table.to_parquet(PROCESSED / f"monitor_{split}.parquet", compression="zstd", index=False)
    alerts = myt.build_alerts(table, outings[[*myt.OUTING, *cfg["features"]["core"]]], cfg["features"]["core"], cal.final_rules(cfg))
    alerts.to_parquet(PROCESSED / f"alerts_{split}.parquet", compression="zstd", index=False)

    log.info("%s 평가 완료: 사례 %d, 대조군 %d, 감시 등판 %d, 경보 %d", split, len(cases), len(controls), len(table), len(alerts))
    pd.set_option("display.width", 230)
    show = results[results["group"] == "all"].set_index("method")
    print(show[["cases", "controls", "concordance", "concordance_lo", "concordance_hi", "detection", "control_window", "diff",
                "diff_lo", "diff_hi", "median_lead", "false_alarms_per100"]].to_string(float_format=lambda v: f"{v:.3f}"))
    print()
    print(pd.DataFrame(tests).to_string(index=False, float_format=lambda v: f"{v:.4f}"))


def h4(cfg: dict, split: str) -> None:
    """H4 (단계 5.5): 불펜 사례의 관찰 창 기간에 부하 채널 표시가 대조군보다 자주 나타나는가.

    표시 기준은 config.load(개발셋에서 정한 값) 그대로 load.parquet에 들어 있다. 사례마다 가장 가까운 대조군(누적 투구 수 차이가
    가장 작은 쪽) 1명을 짝지어 McNemar 정확 검정을 하고, 사례 − 대조군 평균의 부트스트랩 95% CI도 함께 낸다.
    판정: McNemar p < 0.05이고 사례 쪽 표시 비율이 더 높으면 지지. 선발 포함 결과는 참고로 함께 적는다.
    """
    outings, _, cases, controls, windows = split_data(cfg, split)
    load = pd.read_parquet(PROCESSED / "load.parquet")
    flags = [c for c in load.columns if c.startswith("flag_")]
    marks = mt.window_flags(windows, outings, load, flags).merge(cases[["case_id", "role"]], on="case_id")
    nearest = controls.sort_values(["case_id", "dist", "pitcher"]).drop_duplicates("case_id")[["case_id", "pitcher"]]
    reps, seed = cfg["evaluation"]["bootstrap_reps"], cfg["seed"]
    rows = []
    for scope, part in (("RP", marks[marks["role"] == "RP"]), ("all", marks)):
        case = part[part["group"] == "case"].set_index("case_id")
        ctl = part[part["group"] == "control"]
        partner = ctl.merge(nearest, on=["case_id", "pitcher"]).set_index("case_id").reindex(case.index)
        for flag in [*flags, "any"]:
            a, b = case[flag].astype(bool), partner[flag].fillna(False).astype(bool)
            p = mt.mcnemar_exact(a[partner[flag].notna()], b[partner[flag].notna()])
            diff, lo, hi = mt.bootstrap_ci((case[flag].astype(float) - ctl.groupby("case_id")[flag].mean()).dropna(), reps, seed)
            rows.append({"scope": scope, "flag": flag, "cases": len(case), "case_rate": 100 * a.mean(),
                         "control_rate": 100 * ctl[flag].mean(), "nearest_control_rate": 100 * b.mean(),
                         "diff": 100 * diff, "diff_lo": 100 * lo, "diff_hi": 100 * hi, "mcnemar_p": p,
                         "supported": bool(p < 0.05 and a.mean() > b.mean()) if flag == "any" else np.nan})
    table = pd.DataFrame(rows)
    table.to_csv(TABLES / f"{split}_h4_load.csv", index=False, encoding="utf-8-sig")
    verdict = table[(table["scope"] == "RP") & (table["flag"] == "any")].iloc[0]
    log.info("H4 (%s, 불펜 사례 %d): 표시 있음 사례 %.1f%% vs 가장 가까운 대조군 %.1f%%, McNemar p = %.3f → %s", split,
             verdict["cases"], verdict["case_rate"], verdict["nearest_control_rate"], verdict["mcnemar_p"],
             "지지" if verdict["supported"] else "지지 안 됨")
    pd.set_option("display.width", 220)
    print(table.to_string(index=False, float_format=lambda v: f"{v:.3f}"))


def draw_opcurve(points: pd.DataFrame, split: str, cfg: dict) -> None:
    plots.use_style()
    fig, ax = plt.subplots(figsize=(7.5, 5))
    colors = {METHODS["velo"]: plots.SERIES, METHODS["change"]: "#3f9b6c", METHODS["b1"]: "#d9822b", METHODS["b2"]: "#8e6bbf",
              METHODS["b3"]: "#c94f7c", METHODS["b4"]: "#5d9ec7", METHODS["consensus"]: plots.MUTED}
    for name, part in points.groupby("method", sort=False):
        part = part.sort_values("false_alarms_per100")
        ax.plot(part["false_alarms_per100"], part["detection"], marker="o", markersize=4, color=colors[name], label=name)
    ax.axvline(100 / cfg["monitor"]["arl0_target"], color=plots.MUTED, linewidth=0.8, linestyle="--")
    ax.set_xlabel("대조군 100등판당 오경보 수 (점선: 설계점 1회)")
    ax.set_ylabel("탐지율 (%)  관찰 창 안 경보가 있는 사례 비율")
    ax.set_title(f"운영 곡선 ({'개발셋' if split == 'dev' else '검증셋' if split == 'val' else '봉인 평가'}: 한계에 배수 {', '.join(str(s) for s in cfg['evaluation']['opcurve_scales'])}를 곱함)")
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(ROOT / "reports" / "figures" / f"{split}_opcurve.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "val"], required=True, help="dev = 개발셋 시험 실행, val = 검증셋 (고정 뒤)")
    ap.add_argument("--h4", action="store_true", help="불펜 부하 채널 가설(H4)만 계산한다 (단계 5.5)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / f"evaluate_{a.split}.log", encoding="utf-8"), logging.StreamHandler()])
    if a.split == "val" and not frozen():
        raise SystemExit("평가 계획이 아직 고정되지 않았습니다 (docs/eval_plan.md 첫 줄이 FROZEN: true 여야 함). 검증셋은 고정 뒤에 실행합니다.")
    (h4 if a.h4 else evaluate)(load_config(), a.split)


if __name__ == "__main__":
    main()
