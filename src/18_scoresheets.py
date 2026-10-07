"""고교 기록지 사진 판독 (볼·스트라이크·이닝별 투구 수). 설정은 config_kbsa.yaml의 scoresheets.

기록지 사진은 선수 실명이 있어 저장소 밖(scoresheets.dir)에만 둔다. 사진 내려받기도 저장소 밖 스크립트가 한다.

    python -m src.18_scoresheets select     # 시범 경기 고르기 → data/processed/scoresheet_pilot.csv
    python -m src.18_scoresheets list       # 2025 전체 경기의 기록지 사진 목록 → data/processed/scoresheet_all.csv (2026-10-08 사용자 허가: 전체 1회 수집)
    python -m src.18_scoresheets read       # 기록지마다 투구 표시 → data/processed/scoresheets/<사진>.parquet (이미 한 것은 건너뜀)
    python -m src.18_scoresheets train-count  # 맞닿은 표시 개수 모형 (합성 견본, 시험용 경기 제외) → data/processed/scoresheet_count_model.pkl
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
    padded = cv2.copyMakeBorder(gray, 12, 12, 12, 12, cv2.BORDER_REPLICATE)
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
            Y, X = box[1] + m["y"], box[0] + m["x"]
            crop = ss.center_crop(gray, Y + m["h"] // 2, X + m["w"] // 2)
            gctx = padded[Y:Y + m["h"] + 24, X:X + m["w"] + 24]                 # 덩어리 둘레 12px까지 회색 (덩어리는 (12, 12)에서 시작)
            rows.append(dict(game_idx=game_idx, sheet=path.stem, team=pitch_team, bat_team=team, pa=pa_i, inning=p["inning"], slot=p["slot"],
                             cat=kb.pa_category(p["result"]), ibb="고의" in p["result"], number=p.get("pitcher"), idx=i, n=len(ms), col=c[0],
                             **{k: v for k, v in f.items() if k != "pix"}, pix=np.asarray(f["pix"], np.float32).tobytes(),
                             crop=crop.astype(np.uint8).tobytes(), mask=m["mask"].astype(np.uint8).tobytes(), gctx=gctx.astype(np.uint8).tobytes(),
                             gap_up=m["y"] - (ms[i - 1]["y"] + ms[i - 1]["h"]) if i > 0 else 99,
                             gap_dn=ms[i + 1]["y"] - (m["y"] + m["h"]) if i + 1 < len(ms) else 99))
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


INPLAY = {"OUT", "H", "HR", "E", "FC", "SAC"}


def game_split(cfg: dict) -> dict:
    """경기 → 'pilot'/'label'/'test'. 시험용(test) 경기는 어떤 모형 학습·보정에도 쓰지 않는다 (2026-10-08)."""
    sc = cfg["scoresheets"]
    games = pd.read_csv(PROCESSED / "scoresheet_all.csv", encoding="utf-8-sig")["game_idx"]
    pilot = set(pd.read_csv(PROCESSED / "scoresheet_pilot.csv", encoding="utf-8-sig")["game_idx"]) | set(sc.get("dev_games", []))
    return ss.holdout_split(games, pilot, seed=sc["holdout_seed"])


def _blobs(df: pd.DataFrame) -> list[dict]:
    """저장한 덩어리 → 모양(mask)·회색 주변 조각(gctx)·덩어리 회색(gray)."""
    out = []
    for r in df.itertuples():
        h, w = int(r.h), int(r.w)
        mk = np.frombuffer(r.mask, np.uint8).reshape(h, w)
        gctx = np.frombuffer(r.gctx, np.uint8).reshape(h + 24, w + 24)
        out.append(dict(mask=mk, gctx=gctx, gray=gctx[12:12 + h, 12:12 + w]))
    return out


def _sheet_scale(df: pd.DataFrame) -> tuple[float, float, float]:
    return float(df["h"].median()), float(df["w"].median()), float(df["area"].median())


def _count_training(df: pd.DataFrame, rng) -> tuple[list, list]:
    """한 기록지: 진짜 단독 표시(보통 크기·위아래가 떨어진 것 + 초구 타격 타석의 큰 빗금 원) = 1개, 같은 기록지 단독 표시를 쌓은 합성 = 2·3개."""
    df = df[df["keep_rel"]]
    if len(df) < 20:
        return [], []
    h0, w0, a0 = _sheet_scale(df)
    blobs = _blobs(df)
    hr = df["h"].to_numpy() / h0
    iso = (np.minimum(df["gap_up"], df["gap_dn"]) >= 2).to_numpy()
    normal = [b for b, r, i in zip(blobs, hr, iso) if 0.6 <= r <= 1.3 and i]
    tall1 = [b for b, r, n, c in zip(blobs, hr, df["n"], df["cat"]) if r > 1.3 and n == 1 and c in INPLAY]   # 초구 타격 타석: 덩어리 하나 = 표시 하나
    # (2026-10-08 시도: 인플레이 마지막 덩어리 전부를 단독으로 더하면 시험용 상관 +0.609→+0.586, 잘못 자르기 8.7%→11.5%로 나빠져 되돌림)
    X = [ss.count_features(b["mask"], b["gray"], h0, w0, a0) for b in normal + tall1]
    y = [1] * len(X)
    if len(normal) >= 6:
        for k, reps in ((2, 40), (3, 15)):
            for _ in range(reps):
                st = ss.stack_marks([normal[j] for j in rng.choice(len(normal), size=k, replace=False)], rng)
                if st is not None:
                    X.append(ss.count_features(st[0], st[1], h0, w0, a0)); y.append(k)
    return X, y


def _sheet_frames(games: set) -> list[pd.DataFrame]:
    out = []
    for f in sorted(SHEET_OUT.glob("*.parquet")):
        if int(f.stem.split("_")[0]) in games:
            df = pd.read_parquet(f)
            if len(df) and "mask" in df:
                out.append(df)
    return out


def predict_counts(df: pd.DataFrame, model: dict) -> np.ndarray:
    """기록지 하나의 덩어리마다 표시 개수 (1~3). 보정값 beta는 '1개'를 그만큼 더 믿는다."""
    h0, w0, a0 = _sheet_scale(df)
    F = np.array([ss.count_features(b["mask"], b["gray"], h0, w0, a0) for b in _blobs(df)])
    P = model["clf"].predict_proba(F)
    P[:, list(model["clf"].classes_).index(1)] *= model["beta"]
    return model["clf"].classes_[P.argmax(1)]


def train_count(cfg: dict) -> dict:
    split = game_split(cfg)
    train_games = {g for g, s in split.items() if s in ("label", "pilot")}
    frames = _sheet_frames(train_games)
    rng = np.random.default_rng(0)
    order = rng.permutation(len(frames))
    fit_idx, cal_idx = order[: len(frames) // 2], order[len(frames) // 2:]          # 반은 합성 학습, 반은 보정
    X, y = [], []
    for i in fit_idx:
        a, b = _count_training(frames[i], rng); X += a; y += b
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31, random_state=0).fit(np.array(X), np.array(y))
    log.info("개수 모형: 기록지 %d장에서 견본 %d개 (1개 %d · 2개 %d · 3개 %d)", len(fit_idx), len(y), y.count(1), y.count(2), y.count(3))
    cal = [frames[i][frames[i]["keep_rel"] & frames[i]["number"].notna()] for i in cal_idx]
    cal = [c for c in cal if len(c) >= 5]
    off = official_pitchers(sorted({int(c["game_idx"].iat[0]) for c in cal}))
    best = None
    for beta in [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 14.0]:
        model = {"clf": clf, "beta": beta}
        got = pd.concat([c.assign(k=predict_counts(c, model)) for c in cal])
        o = off.merge(got.assign(number=got["number"].astype(int)).groupby(["game_idx", "team", "number"])["k"].sum().rename("marks").reset_index(),
                      on=["game_idx", "team", "number"])
        o = o[o["pitches"] >= cfg["scoresheets"]["judge_min_pitches"]]
        ratio = o["marks"] / o["pitches"]
        score = (float(np.mean((ratio - 1).abs() <= .10)), -abs(float(ratio.median()) - 1))
        log.info("  보정 beta %.2f: 40구+ %d등판 · 셈 비율 중앙 %.3f · ±10%% %.0f%% · ±15%% %.0f%%", beta, len(o), ratio.median(), 100 * score[0],
                 100 * np.mean((ratio - 1).abs() <= .15))
        if best is None or score > best[0]:
            best = (score, beta)
    log.info("보정 beta = %.2f (보정용 기록지 %d장)", best[1], len(cal))
    return {"clf": clf, "beta": best[1]}


def _decode(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["pix"] = [np.frombuffer(b, np.float32) for b in df["pix"]]
    if "crop" in df:
        df["crop"] = [np.frombuffer(b, np.uint8) for b in df["crop"]]
    return df


def ball_inputs(model, df: pd.DataFrame) -> np.ndarray:
    """2차 모형(dict, inputs='shape')은 모양만, 1차 모형(분류기 그대로)은 모양 + 가운데 회색."""
    return ss.shape_matrix(df) if isinstance(model, dict) and model.get("inputs") == "shape" else ss.ball_matrix(df)


def ball_proba(model, df: pd.DataFrame) -> np.ndarray:
    clf = model["clf"] if isinstance(model, dict) else model
    return clf.predict_proba(ball_inputs(model, df))[:, 1]


def train(cfg: dict) -> dict:
    """볼 판정 분류기. 학습 자료에 회색 그림(crop)이 없으면 모양만 쓰는 2차 모형."""
    t = _decode(pd.read_parquet(cfg["scoresheets"]["train_set"]))
    inputs = "shape" if "crop" not in t else "shape+crop"
    clf = HistGradientBoostingClassifier(max_iter=400, learning_rate=0.06, max_leaf_nodes=31, random_state=0)
    clf.fit(ss.shape_matrix(t) if inputs == "shape" else ss.ball_matrix(t), t["label"].astype(int))
    log.info("볼 판정 분류기 학습 (%s): 표시 %d개 (볼 %d · 볼 아님 %d, 출처 %s)", inputs, len(t), int(t["label"].sum()), int((t["label"] == 0).sum()),
             t["source"].value_counts().to_dict())
    return {"clf": clf, "inputs": inputs}


def official_pitchers(game_ids) -> pd.DataFrame:
    rows = []
    for g in game_ids:
        page = RAW / f"record_detail_{g}.html"
        if page.exists():
            for p in kb.parse_record_detail(page.read_text(encoding="utf-8"), int(g))["pitchers"]:
                rows.append(dict(game_idx=int(g), team=p["team"], number=p["number"], pitches=p["pitches"], batters=p["batters"], bb_hbp=p["bb_hbp"]))
    t = pd.DataFrame(rows)
    return t.groupby(["game_idx", "team", "number"], as_index=False)[["pitches", "batters", "bb_hbp"]].sum(min_count=1)   # 한 투수 두 번 등판은 합친다


def sheet_marks(df_all: pd.DataFrame, count_model: dict | None) -> pd.DataFrame:
    """기록지 하나: 덩어리마다 표시 개수를 정하고(개수 모형), 여러 개면 위아래로 잘라 조각마다 볼 판정 입력을 만든다.
    조각의 hr·wr는 판정 학습 때처럼 그 기록지 전체 덩어리(상대 크기 거르기 전)의 높이·너비 중앙값에 대한 비율."""
    h_pre, w_pre = float(df_all["h"].median()), float(df_all["w"].median())
    df = df_all[df_all["keep_rel"]].reset_index(drop=True)
    if len(df) == 0:
        return df
    k = predict_counts(df, count_model) if count_model else np.ones(len(df), int)
    rows = []
    for r, kk, b in zip(df.itertuples(index=False), k, _blobs(df)):
        base = r._asdict()
        if kk <= 1:
            rows.append({**base, "k": 1, "piece": 0})
            continue
        for j, pc in enumerate(ss.split_marks(b["mask"], b["gray"], int(kk))):
            f = ss.shape_features(dict(mask=pc["mask"]))
            ph, pw = pc["mask"].shape
            cy, cx = 12 + pc["y"] + ph // 2, 12 + pc["x"] + pw // 2
            crop = b["gctx"][cy - 12:cy + 12, cx - 12:cx + 12]
            rows.append({**base, **{c: f[c] for c in ss.FEATURES if c in f}, "hr": ph / h_pre, "wr": pw / w_pre,
                         "pix": np.asarray(f["pix"], np.float32).tobytes(), "crop": np.ascontiguousarray(crop, np.uint8).tobytes(), "k": int(kk), "piece": j})
    out = pd.DataFrame(rows)
    return out.drop(columns=[c for c in ("mask", "gctx") if c in out])


def score(cfg: dict, clf) -> pd.DataFrame:
    sc = cfg["scoresheets"]
    cm_path = PROCESSED / "scoresheet_count_model.pkl"
    count_model = pickle.load(open(cm_path, "rb")) if cm_path.exists() else None
    log.info("개수 모형 %s", f"사용 (beta {count_model['beta']})" if count_model else "없음 — 덩어리 하나 = 표시 하나")
    parts = []
    for f in sorted(SHEET_OUT.glob("*.parquet")):
        df = pd.read_parquet(f)
        if len(df) == 0:
            continue
        df = sheet_marks(df, count_model)
        df = _decode(df[df["number"].notna()])
        if len(df) == 0:
            continue
        df["p_ball"] = ball_proba(clf, df)
        parts.append(df.drop(columns=[c for c in ("pix", "crop") if c in df]))
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
    split = game_split(cfg)
    o = o.assign(split=o["game_idx"].map(split))
    rows = []
    for name, part in [("시범 31경기", o[o["split"] == "pilot"]), ("2차 학습용 경기", o[o["split"] == "label"]),
                       ("시험용 경기 (학습·보정에 안 씀)", o[o["split"] == "test"]), ("전체", o)]:
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
    ap.add_argument("step", choices=["select", "list", "read", "train-count", "train", "score"])
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
    if a.step == "train-count":
        with open(PROCESSED / "scoresheet_count_model.pkl", "wb") as fh:
            pickle.dump(train_count(cfg), fh)
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
