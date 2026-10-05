"""불펜 부하 채널 지표 (단계 2.5). 규칙은 docs/SPEC.md 3.11절, 기준선 구간은 3.7절.

등판 표의 전 구종 투구 수(n_all)로 등판마다 연투, 연속 등판 일수, 최근 3일 등판 수, 최근 7일 투구 수, ACWR,
직전 등판 투구 수와 휴식일을 계산하고 표시(flag_*)를 붙여 data/processed/load.parquet로 저장한다.
요약은 개발셋 시즌만 보여 준다.

사용 예:
    python -m src.04_load
    python -m src.04_load --flags-dev     # 개발셋 대조군 불펜의 표시 비율 (단계 2.7, controls.csv가 있어야 함)
"""
from __future__ import annotations

import argparse
import logging

import pandas as pd

from src.common import baseline_window as bw
from src.common import load as ld
from src.common.config import ROOT, load_config

PROCESSED = ROOT / "data" / "processed"
log = logging.getLogger("pitchsignal.load")


def flags_dev(cfg: dict) -> None:
    """개발셋 대조군 불펜의 감시 기간 등판에서 표시별 비율을 낸다. 기준값은 바꾸지 않고, 사례의 등판은 보지 않는다."""
    controls = pd.read_csv(PROCESSED / "controls.csv", encoding="utf-8-sig")
    chosen = controls[controls["season"].isin(cfg["data"]["split"]["dev"]) & (controls["role"] == "RP")]
    windows = bw.baseline_windows(pd.read_parquet(PROCESSED / "outings.parquet"), cfg["baseline"])
    rates = ld.flag_rates(pd.read_parquet(PROCESSED / "load.parquet"), chosen,
                          windows.set_index(["pitcher", "season"])["baseline_end"])
    rates.to_csv(ROOT / "reports" / "tables" / "load_flags_dev.csv", encoding="utf-8-sig", index_label="flag")
    log.info("개발셋 대조군 불펜 %d명의 감시 기간 등판 %d개에서 표시 비율 계산", len(chosen), int(rates["outings"].iloc[0]))
    print(rates.assign(rate=(100 * rates["rate"]).round(1)).rename(columns={"rate": "rate_pct"}).to_string())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--flags-dev", action="store_true", help="개발셋 대조군 불펜의 표시 비율 표를 만든다 (단계 2.7)")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "load.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    if a.flags_dev:
        return flags_dev(cfg)
    outings = pd.read_parquet(PROCESSED / "outings.parquet")
    windows = bw.baseline_windows(outings, cfg["baseline"])
    table = ld.load_table(outings, windows, cfg["load"]).merge(
        outings[["pitcher", "season", "game_pk", "role", "is_start", "n_all"]], on=["pitcher", "season", "game_pk"])
    table.to_parquet(PROCESSED / "load.parquet", compression="zstd", index=False)

    has = windows[windows["n_baseline"] > 0].groupby(["season", "role"]).size().unstack(fill_value=0)
    log.info("부하 지표 %d행 저장. 기준선이 있는 투수-시즌(시즌 × 역할):\n%s", len(table), has.to_string())
    dev = table[table["season"].isin(cfg["data"]["split"]["dev"])]
    flags = [c for c in table.columns if c.startswith("flag_")]
    print("개발셋 등판 중 표시가 켜진 비율 (역할별)")
    print(dev.groupby("role")[flags].mean().T.to_string(float_format=lambda v: f"{100 * v:.1f}%"))
    print("ACWR을 계산할 수 있었던 등판 비율:", dev.groupby("role")["acwr"].apply(lambda s: s.notna().mean()).round(3).to_dict())


if __name__ == "__main__":
    main()
