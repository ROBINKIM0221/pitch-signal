"""등판 표를 공식 박스스코어와 대조한다 (단계 2.3 확인용).

무작위로 고른 경기의 MLB Stats API 박스스코어에서 투수별 투구 수·아웃·피안타·볼넷·선발 여부를 읽어
data/processed/outings.parquet의 n_all·outs·h·bb·is_start와 비교한다.

사용 예:
    python tools/check_outings_boxscore.py --games 20
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common import mlb_api as api  # noqa: E402
from src.common.config import ROOT, load_config  # noqa: E402


def boxscore_lines(game_pk: int, cfg: dict) -> list[dict]:
    a = cfg["data"]["api"]
    box = api.get_json(f"{api.BASE}/game/{game_pk}/boxscore", {}, a["pause_sec"], a["retries"], a["timeout_sec"])
    rows = []
    for side in ("home", "away"):
        for player in box["teams"][side]["players"].values():
            line = player.get("stats", {}).get("pitching", {})
            if "numberOfPitches" not in line:
                continue
            whole, _, third = str(line["inningsPitched"]).partition(".")
            rows.append({"game_pk": game_pk, "pitcher": player["person"]["id"], "box_pitches": line["numberOfPitches"],
                         "box_outs": 3 * int(whole) + int(third or 0), "box_h": line["hits"],
                         "box_bb": line["baseOnBalls"], "box_start": line.get("gamesStarted", 0) == 1})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=20)
    a = ap.parse_args()
    cfg = load_config()
    outings = pd.read_parquet(ROOT / "data" / "processed" / "outings.parquet")
    games = outings["game_pk"].drop_duplicates().sample(a.games, random_state=cfg["seed"])
    box = pd.DataFrame([row for g in games for row in boxscore_lines(int(g), cfg)])
    ours = outings.loc[outings["game_pk"].isin(games), ["game_pk", "pitcher", "n_all", "outs", "h", "bb", "is_start"]]
    both = box.merge(ours, on=["game_pk", "pitcher"], how="outer", indicator=True)
    matched = both[both["_merge"] == "both"]
    print(f"경기 {a.games}개, 박스스코어 투수 등판 {len(box)}개, 등판 표와 짝이 맞은 것 {len(matched)}개, "
          f"한쪽에만 있는 것 {int((both['_merge'] != 'both').sum())}개")
    for name, ours, theirs in (("투구 수", "n_all", "box_pitches"), ("아웃", "outs", "box_outs"),
                               ("피안타", "h", "box_h"), ("볼넷", "bb", "box_bb"), ("선발 여부", "is_start", "box_start")):
        same = matched[ours] == matched[theirs]
        print(f"  {name}: 일치 {int(same.sum())}/{len(matched)}", "" if same.all() else
              f"| 다른 것: {matched.loc[~same, ['game_pk', 'pitcher', ours, theirs]].head(5).to_dict('records')}")


if __name__ == "__main__":
    main()
