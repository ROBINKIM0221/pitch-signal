"""고교 기록지 사진 판독 (볼·스트라이크·이닝별 투구 수). 설정은 config_kbsa.yaml의 scoresheets.

기록지 사진은 선수 실명이 있어 저장소 밖(scoresheets.dir)에만 둔다. 사진 내려받기도 저장소 밖 스크립트가 한다.

    python -m src.18_scoresheets select     # 시범 경기 고르기 → data/processed/scoresheet_pilot.csv
"""
from __future__ import annotations

import argparse
import logging
import re

import numpy as np
import pandas as pd
import yaml

from src.common.config import ROOT

RAW = ROOT / "data" / "raw" / "kbsa"
PROCESSED = ROOT / "data" / "processed"
log = logging.getLogger("pitchsignal.scoresheets")


def load_cfg() -> dict:
    return yaml.safe_load((ROOT / "config_kbsa.yaml").read_text(encoding="utf-8"))


def sheet_links(game_idx: int) -> list[int]:
    """경기 기록 페이지에 걸린 기록지 사진 번호(boxfile_seq). 페이지마다 같은 링크가 두 번 나오므로 순서를 지켜 한 번씩."""
    page = RAW / f"record_detail_{game_idx}.html"
    if not page.exists():
        return []
    return list(dict.fromkeys(int(s) for s in re.findall(r"paper_each_download\?boxfile_seq=(\d+)", page.read_text(encoding="utf-8"))))


def select_pilot(cfg: dict) -> pd.DataFrame:
    """시범 경기: 리그마다 한 경기(기록원 글씨가 다양하도록). 기록지가 두 장이고, 두 팀 모두 판정 기준 이상 던진 등판의 흐름이 복원된 경기만."""
    sc = cfg["scoresheets"]
    games = pd.read_csv(ROOT / cfg["games_csv"], encoding="utf-8-sig")
    games["seqs"] = games["game_idx"].map(sheet_links)
    rows = pd.read_parquet(PROCESSED / "hs_korea_2025_rows.parquet")
    ok = rows[(rows["pitches"] >= sc["judge_min_pitches"]) & rows["flow"].notna()]
    both = ok.groupby("game_idx")["school"].nunique()
    elig = games[games["game_idx"].isin(both[both == 2].index) & (games["seqs"].map(len) == 2)
                 & ~games["game_idx"].isin(sc.get("dev_games", []))]
    rng = np.random.default_rng(cfg["seed"])
    leagues = rng.permutation(sorted(elig["lig_idx"].unique()))[: sc["pilot_games"]]
    pick = pd.concat([elig[elig["lig_idx"] == lig].sample(1, random_state=rng) for lig in leagues])
    pick = pick.sort_values(["date", "game_idx"]).reset_index(drop=True)
    pick["seqs"] = pick["seqs"].map(lambda s: " ".join(map(str, s)))
    log.info("시범 경기 %d개 (리그 %d개, 후보 %d경기) · 기록지 %d장", len(pick), pick["lig_idx"].nunique(), len(elig),
             pick["seqs"].str.split().map(len).sum())
    return pick[["game_idx", "date", "league", "lig_idx", "team1", "team2", "seqs"]]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["select"])
    a = ap.parse_args()
    cfg = load_cfg()
    if a.step == "select":
        out = PROCESSED / "scoresheet_pilot.csv"
        select_pilot(cfg).to_csv(out, index=False, encoding="utf-8-sig")
        log.info("→ %s", out)


if __name__ == "__main__":
    main()
