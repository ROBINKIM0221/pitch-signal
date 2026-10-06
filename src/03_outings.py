"""등판 표 만들기 (단계 2.3). 규칙은 docs/SPEC.md 3.2·3.4·3.5절.

내려받은 Statcast를 시즌별로 읽어
  data/processed/outings.parquet      투수 × 경기 한 줄 (역할, 주력 패스트볼, 투구 수, 특징 F1~F9, 피안타·볼넷·아웃)
  data/processed/pitches_fb.parquet   핵심 특징에 결측이 없는 주력 패스트볼 투구별 특징
수직 릴리스(rel_z)는 두 표 모두 구장 효과를 뺀 값이고, 뺀 값은 등판 표의 park_rel_z에 있다 (SPEC 3.5).
을 만든다. --nmin은 개발셋만으로 투구 수 분포와 특징별 n_min을 내어 적격 등판 하한을 정할 근거를 만든다 (단계 2.4).
성능 지표는 계산하지 않는다.

사용 예:
    python -m src.03_outings
    python -m src.03_outings --nmin
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.common import outings as og
from src.common import park
from src.common import plots
from src.common import statcast as st
from src.common.config import ROOT, load_config
from src.core import stats_core as sc

RAW = ROOT / "data" / "raw" / "statcast"
VENUES = ROOT / "data" / "raw" / "venues.parquet"
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
COLUMNS = ["game_pk", "game_date", "pitcher", "p_throws", "inning", "inning_topbot", "at_bat_number", "pitch_number",
           "pitch_type", "description", "events", "plate_z", "sz_top", "sz_bot", "zone", *og.FEATURE_COLUMNS.values()]
log = logging.getLogger("pitchsignal.outings")


def build(cfg: dict) -> None:
    outings, pitches_fb = [], []
    for season in cfg["data"]["seasons"]:
        o, f = og.build_outings(st.load_season(RAW, season, COLUMNS), season, cfg["features"])
        log.info("%d 시즌: 등판 %d, 적격 등판 %d, 주력 패스트볼 투구 %d", season, len(o), int(o["eligible"].sum()), len(f))
        outings.append(o)
        pitches_fb.append(f)
    outings, pitches_fb = pd.concat(outings, ignore_index=True), pd.concat(pitches_fb, ignore_index=True)
    if not VENUES.exists():
        raise SystemExit("data/raw/venues.parquet가 없습니다. python -m src.01_download --venues 를 먼저 실행하세요.")
    venues = pd.read_parquet(VENUES).rename(columns={"venue_id": "venue"})
    outings = outings.merge(venues[["game_pk", "venue"]], on="game_pk", how="left")
    log.info("구장을 모르는 등판 %d개 (보정 없이 둠)", int(outings["venue"].isna().sum()))
    outings, pitches_fb = park.adjust(outings, pitches_fb, cfg["features"]["park_adjust"])
    for f in cfg["features"]["park_adjust"]["features"]:
        log.info("%s 구장 보정: 보정값 표준편차 %.4f, 보정하지 않은 등판 %.1f%%", f, outings[f"park_{f}"].std(),
                 100 * (outings[f"park_{f}"] == 0).mean())
    outings.to_parquet(PROCESSED / "outings.parquet", compression="zstd", index=False)
    pitches_fb.to_parquet(PROCESSED / "pitches_fb.parquet", compression="zstd", index=False)

    pitchers = outings.drop_duplicates(["season", "pitcher"])
    summary = pd.DataFrame({
        "outings": outings.groupby("season").size(),
        "eligible": outings.groupby("season")["eligible"].sum(),
        "starts": outings.groupby("season")["is_start"].sum(),
        "SP": pitchers[pitchers["role"] == "SP"].groupby("season").size(),
        "RP": pitchers[pitchers["role"] == "RP"].groupby("season").size(),
        **{f"primary_{t}": pitchers[pitchers["primary_fb"] == t].groupby("season").size()
           for t in cfg["features"]["primary_fastball_types"]},
        "no_primary": pitchers[pitchers["primary_fb"].isna()].groupby("season").size(),
        "core_missing_mean": outings.groupby("season")["core_missing_frac"].mean(),
        "core_missing_p95": outings.groupby("season")["core_missing_frac"].quantile(0.95),
    }).fillna(0)
    summary.to_csv(TABLES / "outings_summary.csv", encoding="utf-8-sig")
    print(summary.T.to_string(float_format=lambda v: f"{v:.3f}" if v < 1 else f"{v:.0f}"))
    extra = [c for c in ("rel_x", "extension", "spin") if pitches_fb[c].isna().any()]
    log.info("pitches_fb %d행. 핵심 특징 결측 %d, 그 밖 특징 결측률 %s", len(pitches_fb),
             int(pitches_fb[cfg["features"]["core"]].isna().sum().sum()),
             {c: round(float(pitches_fb[c].isna().mean()), 4) for c in extra})


def nmin_report(cfg: dict) -> None:
    """개발셋만으로 투구 수 분포와 특징별 n_min을 낸다. 하한은 이 표를 보고 사람이 정한다."""
    dev, n, floor = cfg["data"]["split"]["dev"], cfg["features"]["nmin"], cfg["features"]["min_fastballs"]
    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    outings = outings[outings["season"].isin(dev) & outings["primary_fb"].notna()]
    pitches_fb = pd.read_parquet(PROCESSED / "pitches_fb.parquet")
    pitches_fb = pitches_fb[pitches_fb["season"].isin(dev)]

    share = pd.DataFrame({f"n_fb < {t}": outings.groupby("role")["n_fb"].apply(lambda s, t=t: (s < t).mean())
                          for t in n["share_thresholds"]})
    share.to_csv(TABLES / "n_fb_share.csv", encoding="utf-8-sig")

    plots.use_style()
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.6))
    for ax, (role, title) in zip(axes, {"SP": "선발 투수", "RP": "불펜 투수"}.items()):
        counts = outings.loc[outings["role"] == role, "n_fb"]
        top = int(counts.quantile(0.995))
        ax.hist(counts.clip(upper=top), bins=range(0, top + 2), weights=np.full(len(counts), 100 / len(counts)),
                color=plots.SERIES, rwidth=0.82)
        ax.axvline(floor, color=plots.MUTED, linewidth=0.8)
        ax.text(0.98, 0.96, f"세로선: 하한 {floor}구\n하한 미만 등판 {100 * (counts < floor).mean():.1f}%",
                transform=ax.transAxes, ha="right", va="top", color=plots.INK_SECONDARY)
        ax.set_title(f"{title} (등판 {len(counts):,}개)")
        ax.set_xlabel("등판당 주력 패스트볼 투구 수 (상위 0.5%는 마지막 막대에 합침)")
        ax.set_ylabel("등판 비율 (%)")
    fig.suptitle(f"등판당 주력 패스트볼 투구 수, 개발셋 {dev[0]}~{dev[-1]}", x=0.01, ha="left", fontweight="bold")
    fig.tight_layout()
    fig.savefig(ROOT / "reports" / "figures" / "n_fb_hist.png")

    features = list(og.FEATURE_COLUMNS)
    components = og.variance_components(pitches_fb, features, floor, n["min_outings"]).merge(
        outings.drop_duplicates(["pitcher", "season"])[["pitcher", "season", "role"]], on=["pitcher", "season"])
    rows = []
    for group, part in (("전체", components), ("SP", components[components["role"] == "SP"]),
                        ("RP", components[components["role"] == "RP"])):
        for f in features:
            sigma_w, sigma_b = part[f"sigma_w_{f}"].median(), part[f"sigma_b_{f}"].median()
            rows.append({"group": group, "feature": f, "pitcher_seasons": len(part), "sigma_w": sigma_w,
                         "sigma_b": sigma_b, "n_min": sc.n_min(sigma_w, sigma_b)})
    n_min = pd.DataFrame(rows)
    n_min.to_csv(TABLES / "n_min.csv", index=False, encoding="utf-8-sig")

    velo = n_min[(n_min["group"] == "전체") & (n_min["feature"] == "velo")].iloc[0]
    subprocess.run([sys.executable, str(ROOT / "tools" / "sim_short_outings.py"), "--sw", f"{velo['sigma_w']:.4f}",
                    "--sb", f"{velo['sigma_b']:.4f}", "--out", str(TABLES / "sim_short_outings.csv")], check=True)

    print("주력 패스트볼 수가 기준보다 적은 등판의 비율")
    print(share.to_string(float_format=lambda v: f"{100 * v:.1f}%"))
    print()
    print("특징별 σ_w, σ_b(투수-시즌 중앙값)와 n_min = (σ_w/σ_b)²")
    print(n_min.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    relief = outings.loc[outings["role"] == "RP", "n_fb"]
    for candidate in n["floor_candidates"]:
        print(f"하한 {candidate}구: 불펜 등판의 {100 * (relief < candidate).mean():.1f}%가 품질 감시에서 빠짐")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nmin", action="store_true", help="개발셋의 투구 수 분포와 n_min 표를 만든다 (단계 2.4)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "outings.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    nmin_report(cfg) if a.nmin else build(cfg)


if __name__ == "__main__":
    main()
