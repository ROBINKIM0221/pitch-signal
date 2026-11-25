"""기록지 '다시 읽기' 묶음 준비: 다시 읽을 타석 고르기, 묶음(items.json) 만들기, 타석 칸 그림.

묶음 하나 = 폴더 하나(<seq_readings_dir>/<이름>): items.json(타석 목록), tiles/<id>.png·sheet_NN.png(그림), first_pass.json(판독, 읽는 쪽이 채움).
다시 읽을 타석은 두 가지 (2026 시즌과 같은 기준):
  1단계 — 40구 이상인데 검산에 못 미친 등판의 타석
  2단계 — 읽은 표시 수가 투구수 줄의 이닝 투구 수와 2~12구 다른 이닝 칸의 타석 (격자가 의심스러운 장은 뺀다)
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable

import cv2
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from src.common import kbsa_boxscore as kb
from src.common import scoresheet as ss

PER = 60                                    # 묶음당 타석
PAGE = 20                                   # 그림 한 장의 타석 (가로 5칸)
SCALE = 3                                   # 타석 칸 확대 배율
CAT_KO = {"K": "삼진", "BB": "4구", "HBP": "사구", "H": "안타", "HR": "홈런", "OUT": "아웃", "E": "실책", "FC": "야선", "SAC": "희생"}


def hard_outing_keys(outings: pd.DataFrame, games: set[int], min_pitches: int) -> set[tuple[int, str, int]]:
    """1단계 대상 등판 (경기, 던진 팀, 등번호): 범위 안 경기에서 min_pitches 이상이고 검산(gate)에 못 미친 등판."""
    hard = outings[outings["game_idx"].isin(games) & (outings["pitches"] >= min_pitches) & ~outings["gate"].astype(bool)]
    return set(zip(hard["game_idx"].astype(int), hard["team"], hard["number"].astype(int)))


def mismatch_columns(rows: pd.DataFrame, marks: pd.DataFrame, meta: pd.DataFrame, games: set[int],
                     min_diff: int = 2, max_diff: int = 12) -> set[tuple[str, int]]:
    """2단계 대상 이닝 칸 (기록지, 열): |읽은 표시 수 − 투구수 줄의 이닝 투구 수|가 min_diff~max_diff.
    줄 값이 0인 칸, 격자가 의심스러운 장(hy < 0.6 또는 match < 0.5)은 뺀다."""
    r = rows[rows["game_idx"].isin(games)]
    count = marks.groupby(["sheet", "col"]).size().rename("marks").reset_index()
    r = r.merge(count, on=["sheet", "col"], how="left").fillna({"marks": 0})
    bad = set(meta.loc[(meta["hy"] < 0.6) | (meta["match"] < 0.5), "sheet"])
    diff = (r["marks"] - r["pitches"]).abs()
    r = r[(r["pitches"] > 0) & (diff >= min_diff) & (diff <= max_diff) & ~r["sheet"].isin(bad)]
    return set(zip(r["sheet"], r["col"].astype(int)))


def items_for_sheet(sheet: str, game_idx: int, pitch_team: str, pas: list[dict],
                    want: Callable[[dict, tuple[int, int]], bool]) -> list[dict]:
    """기록지 한 장(한 팀 타격)의 타석 가운데 want(타석, (열, 타순))인 것을 묶음 항목으로. 투수를 못 정한 타석과 12열 밖은 뺀다.
    pa 번호는 그 팀 공식 타석의 순서(0부터)다."""
    out = []
    for i, (p, cell) in enumerate(zip(pas, ss.cells_for(pas))):
        if not cell or cell[0] > 12 or p.get("pitcher") is None or not want(p, cell):
            continue
        cat = kb.pa_category(p["result"])
        out.append(dict(id=f"{sheet}_{i}", sheet=sheet, pa=i, mode="pa", inning=int(p["inning"]), col=int(cell[0]), slot=int(cell[1]),
                        result=CAT_KO.get(cat, cat), game_idx=int(game_idx), team=pitch_team, number=int(p["pitcher"]), cat=cat,
                        ibb="고의" in p["result"], blobs=[dict(idx=0, model="-")]))
    return out


def batch_name(season: int, tag: str, stage: int, n: int) -> str:
    """묶음 이름. 이름순 = 주(tag, YYYYMMDD) → 단계 → 번호 순이라, 같은 타석을 나중 묶음이 덮는 규칙과 맞는다."""
    return f"y{season % 100:02d}-{tag}-s{stage}-{n:02d}"


def batches(seq_dir: Path) -> list[Path]:
    return sorted(p for p in Path(seq_dir).iterdir() if (p / "items.json").exists()) if Path(seq_dir).exists() else []


def load_items(batch: Path) -> list[dict]:
    return json.loads((Path(batch) / "items.json").read_text(encoding="utf-8"))


def already_planned(seq_dir: Path) -> set[str]:
    """이미 어느 묶음에 든 타석 id (판독이 끝났든 아니든)."""
    return {it["id"] for b in batches(seq_dir) for it in load_items(b)}


def finished(batch: Path) -> bool:
    """묶음의 모든 타석에 판독이 있으면 끝난 묶음."""
    f = Path(batch) / "first_pass.json"
    if not f.exists():
        return False
    read = json.loads(f.read_text(encoding="utf-8"))
    return all(it["id"] in read for it in load_items(batch))


def write_batches(items: list[dict], seq_dir: Path, season: int, tag: str, stage: int, per: int = PER) -> list[str]:
    """아직 어느 묶음에도 없는 타석만 per개씩 새 묶음으로 쓴다. 만든 묶음 이름들."""
    seen = already_planned(seq_dir)
    new = [it for it in items if it["id"] not in seen]
    names = []
    for n, j in enumerate(range(0, len(new), per), start=1):
        name = batch_name(season, tag, stage, n)
        d = Path(seq_dir) / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "items.json").write_text(json.dumps(new[j:j + per], ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        names.append(name)
    return names


def tile(im, g: dict, k: int, r: int, left: int = 20) -> Image.Image:
    """타석 칸(k열 r행) 그림: SCALE배, 위아래로 칸 높이의 0.3배씩 이웃을 보이고, 왼쪽을 left px 넓게(격자가 밀린 장에서 투구 띠가 잘리지 않게),
    이 타석의 칸에 파란 상자."""
    xl, xr = g["Xr"][r][2 * k], g["Xr"][r][min(2 * k + 2, len(g["Xr"][r]) - 1)]
    yt, yb = g["Yc"][k][r], g["Yc"][k][r + 1]
    rh = yb - yt
    H, W = im.shape[:2]
    x0, x1, y0, y1 = max(0, int(xl) - left), min(W, int(xr) + 4), max(0, int(yt - 0.3 * rh)), min(H, int(yb + 0.3 * rh))
    c = cv2.resize(im[y0:y1, x0:x1], None, fx=SCALE, fy=SCALE, interpolation=cv2.INTER_CUBIC)
    pil = Image.fromarray(cv2.cvtColor(c, cv2.COLOR_BGR2RGB))
    ImageDraw.Draw(pil).rectangle([(xl - x0) * SCALE, (yt - y0) * SCALE, (xr - x0) * SCALE, (yb - y0) * SCALE], outline=(0, 90, 255), width=2)
    return pil


def _font():
    try:
        return ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", 15)
    except OSError:
        return ImageFont.load_default()


def pages(items: list[dict], tiles: list[Image.Image]) -> list[Image.Image]:
    """타석 그림을 PAGE개씩 한 장에 (가로 5칸). 칸 머리 = '#번호 결과 이닝회', 번호는 묶음 안 순서(1부터)."""
    font = _font()
    cw, ch = max(t.width for t in tiles) + 6, max(t.height for t in tiles) + 30
    out = []
    for j in range(0, len(tiles), PAGE):
        n = min(PAGE, len(tiles) - j)
        page = Image.new("RGB", (cw * 5, ch * ((n + 4) // 5)), "white")
        dr = ImageDraw.Draw(page)
        for q, (it, t) in enumerate(zip(items[j:j + PAGE], tiles[j:j + PAGE])):
            X, Y = (q % 5) * cw, (q // 5) * ch
            dr.text((X + 3, Y + 3), f"#{j + q + 1} {it['result']} {it['inning']}회", fill=(200, 0, 0), font=font)
            page.paste(t, (X, Y + 26))
            dr.rectangle([X, Y, X + cw - 2, Y + ch - 2], outline=(0, 0, 0))
        out.append(page)
    return out


def render(batch: Path, photo_dir: Path) -> None:
    """묶음의 그림(tiles/<id>.png, sheet_NN.png)을 만든다. 기록지 사진은 photo_dir/<sheet>.jpg."""
    items = load_items(batch)
    (Path(batch) / "tiles").mkdir(exist_ok=True)
    cache: dict = {}
    tiles = []
    for it in items:
        if it["sheet"] not in cache:
            cache = {it["sheet"]: ss.detect_grid(ss.load(Path(photo_dir) / f"{it['sheet']}.jpg"))}
        im, g = cache[it["sheet"]]
        t = tile(im, g, it["col"] - 1, it["slot"] - 1)
        t.save(Path(batch) / "tiles" / f"{it['id']}.png")
        tiles.append(t)
    for n, page in enumerate(pages(items, tiles), start=1):
        page.save(Path(batch) / f"sheet_{n:02d}.png")


def status(seq_dir: Path) -> dict:
    """묶음 수: 전체·끝남·대기(판독 안 끝남)·그림 있음."""
    bs = batches(seq_dir)
    done = sum(finished(b) for b in bs)
    return {"total": len(bs), "finished": done, "pending": len(bs) - done, "rendered": sum((b / "sheet_01.png").exists() for b in bs)}


def to_render(seq_dir: Path) -> list[Path]:
    """그림을 만들어야 하는 묶음: 판독이 안 끝났고 그림이 없는 것, 이름순."""
    return [b for b in batches(seq_dir) if not finished(b) and not (b / "sheet_01.png").exists()]


def clean(seq_dir: Path) -> int:
    """판독이 끝난 묶음의 그림을 지운다 (items.json·first_pass.json은 남긴다). 지운 묶음 수."""
    n = 0
    for b in batches(seq_dir):
        pictures = [*b.glob("sheet_*.png"), *b.glob("zoom*.png")]
        if finished(b) and ((b / "tiles").exists() or pictures):
            shutil.rmtree(b / "tiles", ignore_errors=True)
            for f in pictures:
                f.unlink()
            n += 1
    return n
