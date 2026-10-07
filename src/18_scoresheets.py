"""고교 기록지 사진 판독 (볼·스트라이크·이닝별 투구 수). 설정은 config_kbsa.yaml의 scoresheets.

기록지 사진은 선수 실명이 있어 저장소 밖(scoresheets.dir)에만 둔다. 사진 내려받기도 저장소 밖 스크립트가 한다.

    python -m src.18_scoresheets select     # 시범 경기 고르기 → data/processed/scoresheet_pilot.csv
    python -m src.18_scoresheets list       # 2025 전체 경기의 기록지 사진 목록 → data/processed/scoresheet_all.csv (2026-10-08 사용자 허가: 전체 1회 수집)
    python -m src.18_scoresheets read       # 기록지마다 투구 표시 → data/processed/scoresheets/<사진>.parquet (이미 한 것은 건너뜀)
    python -m src.18_scoresheets train      # 볼 판정 분류기 (시범 학습 자료, 저장소 밖) → data/processed/scoresheet_ball_model.pkl
    python -m src.18_scoresheets score      # 볼 판정 → 등판별 검산·볼 비율·'평소보다 볼이 많았던 등판' → data/processed/hs_scoresheet_outings.parquet
"""
from __future__ import annotations

import argparse
import logging
import pickle
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier

from src.common import kbsa_boxscore as kb
from src.common import scoresheet as ss
from src.common.config import ROOT

RAW = ROOT / "data" / "raw" / "kbsa"
PROCESSED = ROOT / "data" / "processed"
SHEET_OUT = PROCESSED / "scoresheets"
TABLES = ROOT / "reports" / "tables"
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


def list_all(cfg: dict) -> pd.DataFrame:
    """경기 기록 페이지에 기록지 사진 링크가 있는 2025 경기 전부."""
    games = pd.read_csv(ROOT / cfg["games_csv"], encoding="utf-8-sig")
    games["seqs"] = games["game_idx"].map(sheet_links)
    games = games[games["seqs"].map(len) > 0].copy()
    log.info("기록지가 있는 경기 %d개 · 기록지 %d장", len(games), games["seqs"].map(len).sum())
    games["seqs"] = games["seqs"].map(lambda q: " ".join(map(str, q)))
    return games[["game_idx", "date", "league", "lig_idx", "team1", "team2", "seqs"]]


def game_pas(game_idx: int) -> tuple[dict, dict]:
    """경기 기록 → 팀별 공식 타석(시간 순, 상대 투수 등번호 붙임)."""
    text = (RAW / f"record_detail_{game_idx}.html").read_text(encoding="utf-8")
    game = kb.parse_record_detail(text, game_idx)
    teams = {}
    for team, rows in kb.parse_batting(text).items():
        pas = kb.plate_appearances(rows)
        opp = [p for p in game["pitchers"] if p["team"] != team]
        parts = kb.assign_to_pitchers(pas, [p["batters"] for p in opp])
        for p, part in zip(opp, parts or []):
            for x in part:
                x["pitcher"] = p["number"]
        teams[team] = pas
    return game, teams


def read_sheet(path: Path) -> tuple[pd.DataFrame, dict]:
    """기록지 사진 한 장 → 공식 타석 칸마다 투구 표시(모양 특징·가운데 그림). 선수 이름은 담지 않는다."""
    game_idx = int(path.stem.split("_")[0])
    im, g = ss.detect_grid(ss.load(path))
    ink = ss.ink_mask(im)
    gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    raw = {(k + 1, r + 1): ss.cell_marks(ink, ss.strip_box(g, k, r)) for k in range(12) for r in range(9)}
    game, teams = game_pas(game_idx)
    ranking = ss.match_team({c for c, v in raw.items() if v}, teams)
    team = ranking[0][1]
    pitch_team = next((t for t in game["teams"] if t != team), None)
    rows = []
    for pa_i, (p, c) in enumerate(zip(teams[team], ss.cells_for(teams[team]))):
        if not c or c[0] > 12:
            continue
        box = ss.strip_box(g, c[0] - 1, c[1] - 1)
        ms = [m for m in raw[c] if ss.keep(m)]
        for i, m in enumerate(ms):
            f = ss.shape_features(m)
            crop = ss.center_crop(gray, box[1] + m["y"] + m["h"] // 2, box[0] + m["x"] + m["w"] // 2)
            rows.append(dict(game_idx=game_idx, sheet=path.stem, team=pitch_team, bat_team=team, pa=pa_i, inning=p["inning"], slot=p["slot"],
                             cat=kb.pa_category(p["result"]), ibb="고의" in p["result"], number=p.get("pitcher"), idx=i, n=len(ms), col=c[0],
                             **{k: v for k, v in f.items() if k != "pix"}, pix=np.asarray(f["pix"], np.float32).tobytes(),
                             crop=crop.astype(np.uint8).tobytes()))
    df = pd.DataFrame(rows)
    if len(df):
        df["hr"] = df["h"] / df["h"].median()
        df["wr"] = df["w"] / df["w"].median()
        df["keep_rel"] = ss.keep_relative(df["area"])
    meta = dict(sheet=path.stem, game_idx=game_idx, bat_team=team, match=ranking[0][0], match2=ranking[1][0] if len(ranking) > 1 else 0.0,
                angle=g["angle"], scale=g["a"], margin=g["margin"], hx=g["hx"], hy=g["hy"], marks=len(df))
    return df, meta


def _read_one(path: str) -> dict:
    out = SHEET_OUT / f"{Path(path).stem}.parquet"
    try:
        df, meta = read_sheet(Path(path))
        df.to_parquet(out, index=False)
        return meta
    except Exception as e:                                       # 한 장이 실패해도 나머지는 계속
        return dict(sheet=Path(path).stem, error=f"{type(e).__name__}: {str(e)[:120]}")


def read_all(cfg: dict, workers: int = 4) -> pd.DataFrame:
    SHEET_OUT.mkdir(parents=True, exist_ok=True)
    photos = sorted(Path(cfg["scoresheets"]["dir"]).glob("*.jpg"))
    todo = [str(p) for p in photos if not (SHEET_OUT / f"{p.stem}.parquet").exists()]
    log.info("기록지 사진 %d장 · 이번에 읽을 것 %d장", len(photos), len(todo))
    metas = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, meta in enumerate(ex.map(_read_one, todo, chunksize=4), 1):
            metas.append(meta)
            if i % 100 == 0 or i == len(todo):
                log.info("%d/%d", i, len(todo))
    meta_path = PROCESSED / "scoresheet_read_meta.csv"
    old = pd.read_csv(meta_path, encoding="utf-8-sig") if meta_path.exists() else pd.DataFrame()
    allm = pd.concat([old, pd.DataFrame(metas)]).drop_duplicates("sheet", keep="last") if metas else old
    allm.to_csv(meta_path, index=False, encoding="utf-8-sig")
    if "error" in allm:
        log.warning("읽기 실패 %d장", int(allm["error"].notna().sum()))
    return allm


def _decode(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["pix"] = [np.frombuffer(b, np.float32) for b in df["pix"]]
    df["crop"] = [np.frombuffer(b, np.uint8) for b in df["crop"]]
    return df


def train(cfg: dict) -> HistGradientBoostingClassifier:
    t = _decode(pd.read_parquet(cfg["scoresheets"]["train_set"]))
    clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06, max_leaf_nodes=31, random_state=0)
    clf.fit(ss.ball_matrix(t), t["label"].astype(int))
    log.info("볼 판정 분류기 학습: 표시 %d개 (볼 %d · 볼 아님 %d, 출처 %s)", len(t), int(t["label"].sum()), int((t["label"] == 0).sum()),
             t["source"].value_counts().to_dict())
    return clf


def official_pitchers(game_ids) -> pd.DataFrame:
    rows = []
    for g in game_ids:
        page = RAW / f"record_detail_{g}.html"
        if page.exists():
            for p in kb.parse_record_detail(page.read_text(encoding="utf-8"), int(g))["pitchers"]:
                rows.append(dict(game_idx=int(g), team=p["team"], number=p["number"], pitches=p["pitches"], batters=p["batters"], bb_hbp=p["bb_hbp"]))
    t = pd.DataFrame(rows)
    return t.groupby(["game_idx", "team", "number"], as_index=False)[["pitches", "batters", "bb_hbp"]].sum(min_count=1)   # 한 투수 두 번 등판은 합친다


def score(cfg: dict, clf) -> pd.DataFrame:
    sc = cfg["scoresheets"]
    parts = []
    for f in sorted(SHEET_OUT.glob("*.parquet")):
        df = pd.read_parquet(f)
        if len(df) == 0:
            continue
        df = _decode(df[df["keep_rel"] & df["number"].notna()])
        if len(df) == 0:
            continue
        df["p_ball"] = clf.predict_proba(ss.ball_matrix(df))[:, 1]
        parts.append(df.drop(columns=["pix", "crop"]))
    marks = pd.concat(parts, ignore_index=True)
    marks["ball"] = (marks["p_ball"] >= 0.5).astype(int)
    marks["number"] = marks["number"].astype(int)
    off = official_pitchers(sorted(marks["game_idx"].unique()))
    off = off.merge(marks[["game_idx", "team"]].drop_duplicates(), on=["game_idx", "team"])   # 기록지를 읽은 (경기, 던진 팀)만
    o = ss.usual_flags(ss.outing_table(marks, off, tol=sc["gate_tol"]), min_pitches=sc["judge_min_pitches"], z=sc["flag_z"],
                       min_history=sc["flag_min_history"])
    o = o.merge(off[["game_idx", "team", "number", "batters", "bb_hbp"]], on=["game_idx", "team", "number"], how="left")
    marks.to_parquet(PROCESSED / "hs_scoresheet_marks.parquet", index=False)
    return o


def summary(o: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """검증 요약 (집계만): 검산 통과율, 볼 비율과 공식 4사구율의 순위상관 — 시범 경기와 그 밖 경기를 나눠서."""
    sc = cfg["scoresheets"]
    pilot = set(pd.read_csv(PROCESSED / "scoresheet_pilot.csv", encoding="utf-8-sig")["game_idx"]) | set(sc.get("dev_games", []))
    rows = []
    for name, part in [("시범 31경기", o[o["game_idx"].isin(pilot)]), ("그 밖 경기", o[~o["game_idx"].isin(pilot)]), ("전체", o)]:
        big = part[part["pitches"] >= sc["judge_min_pitches"]]
        ok = big[big["gate"]]
        r = spearmanr(ok["ball_pct"], ok["bb_hbp"] / ok["batters"]) if len(ok) > 5 else (np.nan, np.nan)
        rows.append({"묶음": name, "등판": len(part), f"{sc['judge_min_pitches']}구 이상": len(big), "검산 통과": len(ok),
                     "통과율": round(len(ok) / max(1, len(big)), 3), "볼비율_4사구율_순위상관": round(float(r[0]), 3), "p": float(r[1]),
                     "추정 볼 비율 중앙값": round(float(ok["ball_pct"].median()), 3) if len(ok) else np.nan,
                     "평소보다 볼 많음 표시": int(big["ball_flag"].sum()), "판정한 등판": int(big["z_ball"].notna().sum())})
    return pd.DataFrame(rows)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["select", "list", "read", "train", "score"])
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    cfg = load_cfg()
    if a.step == "select":
        out = PROCESSED / "scoresheet_pilot.csv"
        select_pilot(cfg).to_csv(out, index=False, encoding="utf-8-sig")
        log.info("→ %s", out)
    if a.step == "list":
        out = PROCESSED / "scoresheet_all.csv"
        list_all(cfg).to_csv(out, index=False, encoding="utf-8-sig")
        log.info("→ %s", out)
    if a.step == "read":
        read_all(cfg, a.workers)
    if a.step == "train":
        with open(PROCESSED / "scoresheet_ball_model.pkl", "wb") as fh:
            pickle.dump(train(cfg), fh)
    if a.step == "score":
        with open(PROCESSED / "scoresheet_ball_model.pkl", "rb") as fh:
            clf = pickle.load(fh)
        o = score(cfg, clf)
        o.to_parquet(PROCESSED / "hs_scoresheet_outings.parquet", index=False)
        s = summary(o, cfg)
        s.to_csv(TABLES / "hs_scoresheet_summary.csv", index=False, encoding="utf-8-sig")
        log.info("등판 %d개\n%s", len(o), s.to_string(index=False))


if __name__ == "__main__":
    main()
