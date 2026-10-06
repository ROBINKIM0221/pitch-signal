"""분할 평가 (단계 5.2~5.3). 규칙은 docs/SPEC.md 3.13절. 개발셋으로 시험하고, 검증셋은 평가 계획 고정 뒤에 한 번 돌린다.

    python -m src.08_evaluate --split dev
    python -m src.08_evaluate --split val      # docs/eval_plan.md가 FROZEN: true 일 때만
    python -m src.08_evaluate --split dev --h4 # H4: 불펜 사례·대조군의 관찰 창 기간 부하 표시 (단계 5.5)
    python -m src.08_evaluate --split val --sensitivity   # 민감도·하위 그룹·실패 분석 (단계 5.4). 주 결과·설정은 바꾸지 않음
2026 봉인 평가는 09_sealed로만 실행한다.

결과 (reports/tables): <split>_results.csv(방법별 지표), <split>_false_alarms.csv(역할·시즌별 오경보),
<split>_tests.csv(가설 판정과 McNemar·Holm), <split>_opcurve.csv와 reports/figures/<split>_opcurve.png(운영 곡선).
대시보드용: data/processed/monitor_<split>.parquet, alerts_<split>.parquet.
"""
from __future__ import annotations

import argparse
import logging

import numpy as np
import pandas as pd

from src.common import baseline_window as bw
from src.common import calibration as cal
from src.common import comparators as cp
from src.common import metrics as mt
from src.common import monitoring as mon
from src.common import pipeline
from src.common.config import ROOT, load_config
from src.common.evaluation import METHODS, evaluate_split, frozen, split_data
from src.core import stats_core as sc

PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
log = logging.getLogger("pitchsignal.evaluate")


def evaluate(cfg: dict, split: str) -> None:
    evaluate_split(cfg, split)


def _tables_for(cfg: dict, rules: dict, seasons_eval: list[int], mean_n: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """개발셋·주어진 분할의 표준화 표를 다른 기준선 규칙(rules)으로 다시 만든다. 합동 역동(config_calibrated)은 그대로 쓴다.

    mean_n=True면 등판마다의 투구 수 대신 투수-시즌 평균 투구 수를 써서 '분산 하나로 처리'한 경우를 흉내 낸다.
    """
    core = cfg["features"]["core"]
    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    pitches_fb = pd.read_parquet(PROCESSED / "pitches_fb.parquet")
    out = []
    for seasons in (cfg["data"]["split"]["dev"], seasons_eval):
        o = outings[outings["season"].isin(seasons)].copy()
        if mean_n:
            o["n_fb_real"] = o["n_fb"]
            o["n_fb"] = o.groupby(["pitcher", "season"])["n_fb"].transform("mean").round().clip(lower=1)
        fits = mon.start_up_table(o, mon.outing_arrays(pitches_fb[pitches_fb["season"].isin(seasons)], core), rules)
        table = mon.dynamic_table(o, fits, pipeline.dynamics_from_config(cfg), rules, core,
                                  sc.t2_ucl(len(core), rules["refine_alpha"])).sort_values(bw.ORDER)
        if mean_n:
            table = table.merge(o[[*cp.OUTING, "n_fb_real"]], on=cp.OUTING)
        out.append(table.reset_index(drop=True))
    return out[0], out[1]



def _controls_of(table: pd.DataFrame, controls: pd.DataFrame) -> np.ndarray:
    return pd.MultiIndex.from_frame(table[["pitcher", "season"]]).isin(pd.MultiIndex.from_frame(controls[["pitcher", "season"]]))


def _fit_rules(dev_table: pd.DataFrame, dev_controls: pd.DataFrame, cfg: dict, lam: float) -> dict:
    """개발셋 대조군으로 두 신호의 한계를 역할별로 다시 맞춘다 (민감도 설정용. config에는 쓰지 않음)."""
    core, m = cfg["features"]["core"], cfg["monitor"]
    is_control, rules = _controls_of(dev_table, dev_controls), {}
    for role in ("SP", "RP"):
        ctl = dev_table[is_control & (dev_table["role"] == role).to_numpy()]
        seqs = cal.sequences(ctl, core)
        t2 = cal.t2_limit(ctl["t2"].to_numpy(), sc.t2_ucl(len(core), m["t2_alpha"]), m["t2_max_far_per100"])
        rules[role] = (cal.fit_velo([uv for _, uv in seqs], lam, 100 / m["arl0_target"], tol=0.02),
                       cal.fit_change([u for u, _ in seqs], lam, t2, 100 / m["arl0_target"], tol=0.02))
    return rules


def _signal_summary(table: pd.DataFrame, windows: pd.DataFrame, cases: pd.DataFrame, controls: pd.DataFrame, cfg: dict,
                    setting: str) -> list[dict]:
    """한 설정에서 두 신호의 검증셋 지표. 관찰 창 등판이 그 설정에서 감시 대상이 아닌 사례·대조군은 뺀다."""
    rows, is_control = [], _controls_of(table, controls)
    have = windows.merge(table[cp.OUTING], on=cp.OUTING, how="left", indicator=True)
    complete = have.groupby(["case_id", "group", "pitcher"])["_merge"].apply(lambda s: (s == "both").all()).reset_index()
    usable = windows.merge(complete[complete["_merge"]][["case_id", "group", "pitcher"]], on=["case_id", "group", "pitcher"])
    for key, name in (("velo", METHODS["velo"]), ("change", METHODS["change"])):
        r = mt.window_results(usable, table, alarm=f"{key}_alarm", index=f"{key}_index")
        d = mt.detection(r)
        conc, lo, hi = mt.bootstrap_ci(mt.concordance(r), cfg["evaluation"]["bootstrap_reps"], cfg["seed"])
        rows.append({"setting": setting, "method": name, "cases": d["cases"], "controls": d["controls"],
                     "concordance": conc, "concordance_lo": lo, "concordance_hi": hi, "detection": 100 * d["detection_rate"],
                     "control_window": 100 * d["control_window_rate"], "median_lead": d["median_lead"],
                     "false_alarms_per100": 100 * table.loc[is_control, f"{key}_alarm"].mean()})
    return rows


def sensitivity(cfg: dict, split: str) -> None:
    """민감도·하위 그룹·실패 분석 (단계 5.4). 주 결과(<split>_results.csv)와 설정 파일은 바꾸지 않는다."""
    core, m, seasons = cfg["features"]["core"], cfg["monitor"], cfg["data"]["split"][split]
    _, _, cases, controls, windows = split_data(cfg, split)
    dev_controls = pd.read_csv(PROCESSED / "controls.csv", encoding="utf-8-sig")
    dev_controls = dev_controls[dev_controls["season"].isin(cfg["data"]["split"]["dev"])]
    dev_table = pd.read_parquet(PROCESSED / "monitor_dev.parquet").sort_values(bw.ORDER).reset_index(drop=True)
    main_table = pd.read_parquet(PROCESSED / f"monitor_{split}.parquet")

    rows = _signal_summary(main_table, windows, cases, controls, cfg, "주 결과 (λ 0.2, 선발 기준선 8)")
    for lam in m["sensitivity_lambdas"]:                                                   # λ: 개발셋에서 한계를 다시 맞춤
        rules = _fit_rules(dev_table, dev_controls, cfg, lam)
        rows += _signal_summary(cal.table_signals(main_table.drop(columns=[c for c in main_table.columns if c.endswith("_alarm") or c.endswith("_index")]),
                                                  core, rules), windows, cases, controls, cfg, f"λ {lam}")
    for length in cfg["evaluation"]["sensitivity"]["starter_baseline_outings"]:          # 선발 기준선 길이
        if length == cfg["baseline"]["starter_outings"]:
            continue
        rules_b = {**cfg["baseline"], "starter_outings": length}
        dev_alt, val_alt = _tables_for(cfg, rules_b, seasons)
        rules = _fit_rules(dev_alt, dev_controls, cfg, m["lam"])
        rows += _signal_summary(cal.table_signals(val_alt, core, rules), windows, cases, controls, cfg, f"선발 기준선 {length}등판")
    sens = pd.DataFrame(rows)
    sens.to_csv(TABLES / "sensitivity.csv", index=False, encoding="utf-8-sig")

    # 분산 하나로 처리 vs 가변 표본 표준화: 투구 수 구간별 대조군 오경보 (구속 하락 신호)
    dev_alt, val_alt = _tables_for(cfg, cfg["baseline"], seasons, mean_n=True)
    rules = _fit_rules(dev_alt, dev_controls, cfg, m["lam"])
    one = cal.table_signals(val_alt, core, rules)
    edges = m["calibration_plot"]["n_bins"]
    labels = [f"{a}~{b - 1}" for a, b in zip(edges, edges[1:])] + [f"{edges[-1]}+"]
    compare = []
    for name, t, n_col in (("가변 표본 표준화 (채택)", main_table, "n_fb"), ("분산 하나로 처리", one, "n_fb_real")):
        ctl = t[_controls_of(t, controls)]
        bins = pd.cut(ctl[n_col], [*edges, np.inf], right=False, labels=labels)
        for role in ("SP", "RP"):
            part = ctl[ctl["role"] == role]
            g = part.groupby(bins[ctl["role"] == role], observed=True)["velo_alarm"]
            for b, rate, n in zip(g.mean().index, g.mean(), g.size()):
                compare.append({"treatment": name, "role": role, "n_fb_bin": b, "outings": int(n), "false_alarms_per100": 100 * rate})
    compare = pd.DataFrame(compare)
    compare.to_csv(TABLES / "sensitivity_by_n.csv", index=False, encoding="utf-8-sig")

    # 하위 그룹: 주 결과 표에서
    results = pd.read_csv(TABLES / f"{split}_results.csv", encoding="utf-8-sig")
    sub = results[results["group"].isin(["SP", "RP", "elbow", "shoulder"])]
    sub.to_csv(TABLES / "subgroups.csv", index=False, encoding="utf-8-sig")

    # 놓친 사례
    people = pd.read_parquet(ROOT / "data" / "raw" / "people.parquet").set_index("id")["full_name"]
    r = mt.window_results(windows, main_table, alarm="velo_alarm", index="velo_index")
    r_change = mt.window_results(windows, main_table, alarm="change_alarm", index="change_index")
    hit = r[r["group"] == "case"].set_index("case_id")
    missed = cases[cases["case_id"].isin(hit.index[~hit["hit"]])].copy()
    order = main_table.groupby(["pitcher", "season"]).cumcount() + 1
    main_table = main_table.assign(order=order)
    w = windows[windows["group"] == "case"].merge(main_table[[*cp.OUTING, "game_date", "order", "n_fb", "velo_index", "change_index"]], on=cp.OUTING)
    feats = w.sort_values("game_date").groupby("case_id").agg(
        first_window_order=("order", "min"), gap_days_mean=("game_date", lambda d: d.diff().dt.days.mean()),
        n_fb_mean=("n_fb", "mean"), velo_index_max=("velo_index", "max"), change_index_max=("change_index", "max"))
    missed = missed.merge(feats, left_on="case_id", right_index=True, how="left")
    missed["name"] = missed["pitcher"].map(people)
    missed["change_hit"] = missed["case_id"].map(r_change[r_change["group"] == "case"].set_index("case_id")["hit"])
    missed["right_after_start_up"] = missed["first_window_order"] <= 2
    missed[["case_id", "name", "season", "role", "part", "il_date", "age", "first_window_order", "right_after_start_up", "gap_days_mean",
            "n_fb_mean", "velo_index_max", "change_index_max", "change_hit"]].to_csv(TABLES / "failures.csv", index=False, encoding="utf-8-sig")

    log.info("민감도 %d줄, 하위 그룹 %d줄, 놓친 사례 %d건 저장", len(sens), len(sub), len(missed))
    pd.set_option("display.width", 230)
    print(sens.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print()
    print(compare.pivot_table(index=["role", "n_fb_bin"], columns="treatment", values="false_alarms_per100", sort=False, observed=True)
          .to_string(float_format=lambda v: f"{v:.2f}"))
    print()
    print("놓친 사례 요약: 역할", missed["role"].value_counts().to_dict(), "| 부위", missed["part"].value_counts().to_dict(),
          "| 시작 구간 직후(창이 감시 1~2번째에서 시작)", int(missed["right_after_start_up"].sum()),
          "| 폼 변화 신호는 울림", int(missed["change_hit"].sum()))
    print("놓친 사례의 창 지수 최댓값 중앙값:", round(missed["velo_index_max"].median(), 2), "(1 이상이면 경보)")


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["dev", "val"], required=True, help="dev = 개발셋 시험 실행, val = 검증셋 (고정 뒤)")
    ap.add_argument("--h4", action="store_true", help="불펜 부하 채널 가설(H4)만 계산한다 (단계 5.5)")
    ap.add_argument("--sensitivity", action="store_true", help="민감도·하위 그룹·실패 분석 (단계 5.4)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / f"evaluate_{a.split}.log", encoding="utf-8"), logging.StreamHandler()])
    if a.split == "val" and not frozen():
        raise SystemExit("평가 계획이 아직 고정되지 않았습니다 (docs/eval_plan.md 첫 줄이 FROZEN: true 여야 함). 검증셋은 고정 뒤에 실행합니다.")
    (sensitivity if a.sensitivity else h4 if a.h4 else evaluate)(load_config(), a.split)


if __name__ == "__main__":
    main()
