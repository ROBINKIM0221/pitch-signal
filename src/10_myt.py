"""경보 원인 분해 (단계 4.6). 규칙은 docs/SPEC.md 3.10절. 개발셋(monitor_dev.parquet)의 경보마다 카드 문구와 분해를 만든다.

최종 한계(config_calibrated.yaml monitor.final)로 울린 경보를 대상으로 하며, 검증셋·봉인 평가의 경보는 08_evaluate·09_sealed가
같은 함수(src/common/myt.build_alerts)로 만든다.

사용 예:
    python -m src.10_myt
"""
from __future__ import annotations

import logging

import pandas as pd

from src.common import calibration as cal
from src.common import myt
from src.common.config import ROOT, load_config

PROCESSED = ROOT / "data" / "processed"
log = logging.getLogger("pitchsignal.myt")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "myt.log", encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config()
    core = cfg["features"]["core"]
    table = pd.read_parquet(PROCESSED / "monitor_dev.parquet")
    if "velo_alarm" not in table.columns:
        raise SystemExit("monitor_dev.parquet에 신호 열이 없습니다. python -m src.06_monitor --calibrate 를 먼저 실행하세요.")
    means = pd.read_parquet(PROCESSED / "outings.parquet", columns=[*myt.OUTING, *core])
    alerts = myt.build_alerts(table, means, core, cal.final_rules(cfg))
    alerts.to_parquet(PROCESSED / "alerts_dev.parquet", compression="zstd", index=False)

    log.info("개발셋 경보 %d건 (감시 등판 %d개) → %s", len(alerts), len(table), PROCESSED / "alerts_dev.parquet")
    print(alerts.groupby(["signal", "rule", "role"]).size().unstack(fill_value=0).to_string())
    pd.set_option("display.width", 200, "display.max_colwidth", 80)
    sample = alerts.sample(min(6, len(alerts)), random_state=cfg["seed"])
    print("\n경보 카드 예 (무작위 6건)")
    print(sample[["role", "game_date", "signal", "rule", "index", "card"]].to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    change = alerts[alerts["signal"] == "change"]
    if len(change):
        top = change[[f"step_{f}" for f in core]].idxmax(axis=1).str.replace("step_", "").map(myt.LABELS)
        print("\n폼 변화 경보에서 몫이 가장 큰 특징:", top.value_counts().to_dict())


if __name__ == "__main__":
    main()
