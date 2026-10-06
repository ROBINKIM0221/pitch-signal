"""사후 지표(사전 등록 아님): 경보가 울린 등판 뒤 30일 안에 팔 부상 IL이 있었던 비율 vs 경보 없는 등판.

분할(dev·val·sealed)과 신호(구속 하락·폼 변화·B1·B4)별로 계산해 reports/tables/alarm_followup.csv에 쓴다.
라벨은 data/processed/labels.csv(최종 팔꿈치·어깨 IL)를 쓴다. 평가 계획의 가설과 무관한 참고 지표다.

    python tools/alarm_followup.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))        # 저장소 어디서 실행해도 src를 찾게
from src.common import metrics as mt  # noqa: E402
from src.common.config import ROOT, load_config  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
SIGNALS = {"velo_alarm": "구속 하락 신호", "change_alarm": "폼 변화 신호", "b1_alarm": "B1 구속 1mph", "b4_alarm": "B4 구속 EWMA(양방향)"}


def main() -> None:
    cfg = load_config()
    labels = pd.read_csv(PROCESSED / "labels.csv", encoding="utf-8-sig", parse_dates=["il_date"])
    labels = labels[labels["part"].isin(["elbow", "shoulder"])]
    rows = []
    for split in ("dev", "val", "sealed"):
        path = PROCESSED / f"monitor_{split}.parquet"
        if not path.exists():
            continue
        table = pd.read_parquet(path)
        seasons = cfg["data"]["split"][split]
        for alarm, name in SIGNALS.items():
            for role in ("all", "SP", "RP"):
                part = table if role == "all" else table[table["role"] == role]
                out = mt.alarm_followup(part, labels[labels["season"].isin(seasons)], days=30, alarm=alarm)
                rows.append({"split": split, "seasons": "~".join(str(s) for s in (seasons[0], seasons[-1])) if len(seasons) > 1 else str(seasons[0]),
                             "method": name, "role": role, **out})
    table = pd.DataFrame(rows)
    table.to_csv(ROOT / "reports" / "tables" / "alarm_followup.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.width", 200)
    show = table[table["role"] == "all"][["split", "method", "alarms", "alarm_rate", "other_rate", "lift"]].copy()
    show[["alarm_rate", "other_rate"]] = (100 * show[["alarm_rate", "other_rate"]]).round(1)
    print(show.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
