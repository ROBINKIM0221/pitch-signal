"""기록지 다시 읽기 묶음 준비. 설정은 config_kbsa.yaml의 scoresheets(seq_readings_dir·dir)와 datasets.

점수 단계(18_scoresheets score·innings) 뒤에 돌린다. 판독이 채워진 묶음은 다음 점수 단계가 읽어 그 타석에 쓴다.

    python -m src.19_reread plan --dataset korea_2027 --tag 20270308   # 다시 읽을 타석을 60개씩 묶음으로 (1단계 → 2단계, 이미 묶인 타석은 뺀다)
    python -m src.19_reread render --max 40                           # 판독이 안 끝났고 그림이 없는 묶음의 그림 만들기 (이름순, 최대 N묶음)
    python -m src.19_reread clean                                     # 판독이 끝난 묶음의 그림 지우기
    python -m src.19_reread status                                    # 묶음 수 (JSON 한 줄)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.common import hs_records as hr
from src.common import kbsa_boxscore as kb
from src.common import reread
from src.common.config import ROOT

RAW = ROOT / "data" / "raw" / "kbsa"
PROCESSED = ROOT / "data" / "processed"


def plan(cfg: dict, key: str, tag: str) -> dict:
    sc = cfg["scoresheets"]
    games = hr.dataset_game_ids(cfg, key)
    outings_path, meta_path = PROCESSED / "hs_scoresheet_outings.parquet", PROCESSED / "scoresheet_read_meta.csv"
    if not games or not outings_path.exists() or not meta_path.exists():
        return {"stage1": [], "stage2": [], "hard_outings": 0, "mismatch_columns": 0}
    meta = pd.read_csv(meta_path, encoding="utf-8-sig")
    meta = meta[meta["error"].isna()] if "error" in meta else meta
    meta = meta[meta["game_idx"].isin(games)]
    keys = reread.hard_outing_keys(pd.read_parquet(outings_path), games, sc["judge_min_pitches"])
    rows_path = PROCESSED / "hs_scoresheet_rows.parquet"
    cols = set()
    if rows_path.exists():
        marks = pd.read_parquet(PROCESSED / "hs_scoresheet_marks.parquet", columns=["sheet", "col", "pa"])
        cols = reread.mismatch_columns(pd.read_parquet(rows_path), marks, meta, games)
    first, second = [], []
    for m in meta.sort_values("sheet").itertuples():
        page = RAW / f"record_detail_{int(m.game_idx)}.html"
        if not page.exists():
            continue
        game, teams = kb.game_pas(page.read_text(encoding="utf-8"), int(m.game_idx))
        pas = teams.get(m.bat_team)
        pitch_team = next((t for t in game["teams"] if t != m.bat_team), None)
        if not pas or pitch_team is None:
            continue
        g, sheet = int(m.game_idx), m.sheet
        first += reread.items_for_sheet(sheet, g, pitch_team, pas, lambda p, cell: (g, pitch_team, int(p["pitcher"])) in keys)
        second += reread.items_for_sheet(sheet, g, pitch_team, pas, lambda p, cell: (sheet, cell[0]) in cols)
    seq_dir, season = Path(sc["seq_readings_dir"]), int(cfg["datasets"][key]["season"])
    s1 = reread.write_batches(first, seq_dir, season, tag, 1)
    s2 = reread.write_batches(second, seq_dir, season, tag, 2)        # 1단계에 든 타석은 여기서 빠진다
    return {"stage1": s1, "stage2": s2, "hard_outings": len(keys), "mismatch_columns": len(cols)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["plan", "render", "clean", "status"])
    ap.add_argument("--dataset", help="plan: 이 데이터셋의 경기에서 고른다")
    ap.add_argument("--tag", help="plan: 묶음 이름에 넣을 날짜 (YYYYMMDD)")
    ap.add_argument("--max", type=int, default=40, help="render: 한 번에 그림을 만들 묶음 수")
    a = ap.parse_args()
    cfg, _ = hr.datasets_config()
    sc = cfg["scoresheets"]
    seq_dir = Path(sc["seq_readings_dir"])
    if a.step == "plan":
        if not a.dataset or not a.tag:
            raise SystemExit("plan에는 --dataset과 --tag가 필요합니다.")
        print(json.dumps(plan(cfg, a.dataset, a.tag), ensure_ascii=False))
    if a.step == "render":
        todo = reread.to_render(seq_dir)[:a.max]
        for b in todo:
            reread.render(b, Path(sc["dir"]))
        print(json.dumps({"rendered": [b.name for b in todo]}, ensure_ascii=False))
    if a.step == "clean":
        print(json.dumps({"cleaned": reread.clean(seq_dir)}))
    if a.step == "status":
        print(json.dumps(reread.status(seq_dir)))


if __name__ == "__main__":
    main()
