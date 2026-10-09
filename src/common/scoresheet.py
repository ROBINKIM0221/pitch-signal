"""고교 기록지 사진 판독: 격자 찾기 → 투구 표시 떼어 내기 → 공식 타석에 잇기 → 볼 비율·검산·'평소보다 볼이 많았던 등판'.

기록지는 KBSA 인쇄 양식 하나다. 기준 기록지(너비 1600px)에서 잰 양식 좌표:
  이닝 칸 왼쪽 경계 TL 13개(12회 오른쪽 포함), 투구 표시 띠 오른쪽 경계 TS = TL + 16 (12개), 타순 줄 높이 ROW_H.
띠 경계선(TS)은 타순 1~9줄에만 있다. 이 '16px 간격 선 쌍'과 '9줄 창'으로 사진마다 격자를 찾고, 줄·칸마다 가까운 선에 붙인다.
표기: 대시(\\ — /) = 볼, 작은 원 = 루킹 스트라이크, 빗금 원 = 헛스윙·타격, 세모 = 파울 (시범 31경기에서 타석 결과로 확인).
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from scipy.ndimage import maximum_filter1d, uniform_filter1d

WIDTH = 1600
TL = np.array([299, 373, 447, 521, 594, 667, 741, 815, 889, 963, 1039, 1115, 1192], float)
TS = TL[:12] + 16.0
TX = np.sort(np.r_[TL, TS])                     # 25개: L1,S1,L2,S2,...,L12,S12,L13
ROW_H = 60.3
NAME_COL = (184, 291)                           # 이닝 1 왼쪽 이름 칸: 긴 세로선이 없어야 한다
FEATURES = ["w", "h", "area", "fill", "elong", "ang", "holes", "enclosed", "solidity", "aspect", "hr", "wr"]


# ---------- 사진 → 격자 ----------

def load(path: str | Path, width: int = WIDTH) -> np.ndarray:
    im = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
    s = width / im.shape[1]
    return cv2.resize(im, (width, int(round(im.shape[0] * s))), interpolation=cv2.INTER_AREA)


def line_masks(im: np.ndarray, k: int = 41) -> tuple[np.ndarray, np.ndarray]:
    """인쇄선: 어두운 화소 중 가로(세로)로 k px 이상 이어진 것."""
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    d = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 31, 12)
    h = cv2.morphologyEx(d, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1)))
    v = cv2.morphologyEx(d, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, k)))
    return h, v


def deskew_angle(v: np.ndarray) -> float:
    n, lab, st, _ = cv2.connectedComponentsWithStats(v, 8)
    slopes = []
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        if h < 300:
            continue
        ys, xs = np.nonzero(lab[y:y + h, x:x + w] == i)
        slopes.append(np.polyfit(ys, xs, 1)[0])
    return float(np.degrees(np.arctan(np.median(slopes)))) if slopes else 0.0


def rotate(img: np.ndarray, deg: float, border) -> np.ndarray:
    h, w = img.shape[:2]
    M = cv2.getRotationMatrix2D((w / 2, h / 2), -deg, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderValue=border)


def _name_penalty(colp: np.ndarray, a: float, bs: np.ndarray, W: int) -> np.ndarray:
    cs = np.r_[0, np.cumsum(colp)]
    lo = np.clip(np.round(a * NAME_COL[0]) + bs, 0, W).astype(int)
    hi = np.clip(np.round(a * NAME_COL[1]) + bs, 0, W).astype(int)
    return 3 * (cs[hi] - cs[lo])


def comb_x(v: np.ndarray) -> tuple[float, float, float, float]:
    """이닝 칸 세로선 25개를 빗으로 찾는다: x = a·TX + b. (a, b, 점수, ±30px 밖 최고 점수와의 차)."""
    H, W = v.shape
    band = v[int(.15 * H):int(.75 * H)]
    colp = band.sum(0).astype(float) / 255 / band.shape[0]
    colm = maximum_filter1d(colp, 5)
    bs = np.arange(-300, 301)

    def scores(a):
        idx = np.round(a * TX)[:, None] + bs[None, :]
        ok = (idx >= 0) & (idx < W)
        return np.where(ok, colm[np.clip(idx, 0, W - 1).astype(int)], 0).sum(0) - _name_penalty(colp, a, bs, W)

    best = (-np.inf, 1.0, 0.0)
    for a in np.arange(0.86, 1.141, 0.002):
        sc = scores(a)
        j = int(np.argmax(sc))
        if sc[j] > best[0]:
            best = (float(sc[j]), float(a), float(bs[j]))
    score, a, b = best
    sc = scores(a)
    far = np.abs(bs - b) > 30
    return a, b, score, score - float(sc[far].max())


def row_window(v: np.ndarray, h: np.ndarray, X: np.ndarray, a: float, spacing: tuple[float, float] = (0.96, 1.04)) -> tuple[int, int, float]:
    """띠 경계선이 있는 9줄 창: 안쪽의 띠 경계선 양은 많고 바로 위(머리 줄)·아래(10번째 줄)는 적은 곳. 위·아래는 가로선에 붙인다.
    spacing = 줄 간격 찾는 범위(가로 배율 a 대비). 세로로 늘어난 사진은 detect_grid 가 넓은 범위로 다시 찾는다."""
    H, W = v.shape
    r = np.zeros(H)
    for c in [int(round(x)) for x in X[1:24:2]]:
        r += v[:, max(0, c - 3):min(W, c + 4)].max(1).astype(float) / 255
    cs = np.r_[0, np.cumsum(r)]
    x0, x1 = int(X[0]) + 3, int(X[-1]) - 3
    hp = uniform_filter1d(h[:, x0:x1].sum(1).astype(float) / 255, 3)
    best = None
    for sp in np.arange(spacing[0], spacing[1] + 0.001, 0.01) * ROW_H * a:
        n = int(9 * sp); s1 = int(sp)
        tops = np.arange(s1, H - n - s1)
        if len(tops) == 0:
            continue
        sc = (cs[tops + n] - cs[tops]) / n - 0.5 * ((cs[tops] - cs[tops - s1]) / s1 + (cs[tops + n + s1] - cs[tops + n]) / s1)
        j = int(np.argmax(sc))
        if best is None or sc[j] > best[0]:
            best = (float(sc[j]), int(tops[j]), sp)
    score, top, sp = best

    def nearest_line(y):
        lo, hi = max(0, int(y) - 8), min(H, int(y) + 9)
        j = lo + int(np.argmax(hp[lo:hi]))
        return j if hp[j] >= 0.4 * (x1 - x0) else int(round(y))

    return nearest_line(top), nearest_line(top + 9 * sp), score


def snap(prof: np.ndarray, pred: np.ndarray, tol: int, min_val: float) -> tuple[np.ndarray, np.ndarray]:
    """예측 위치마다 ±tol 안에서 선(3px 합)이 가장 진한 곳으로. min_val 미만이면 예측 그대로."""
    out = np.array(pred, float).copy(); hit = np.zeros(len(pred), bool)
    sm = uniform_filter1d(np.asarray(prof, float), 3) * 3
    for i, x in enumerate(pred):
        lo, hi = int(max(0, round(x) - tol)), int(min(len(sm), round(x) + tol + 1))
        if hi > lo:
            j = lo + int(np.argmax(sm[lo:hi]))
            if sm[j] >= min_val:
                out[i], hit[i] = j, True
    return out, hit


def detect_grid(im: np.ndarray) -> tuple[np.ndarray, dict]:
    """기울기를 바로잡은 사진과 격자: Xr[줄 0..8][25 세로선], Yc[칸 0..11][10 가로선]과 맞춤 품질."""
    h, v = line_masks(im)
    ang = deskew_angle(v)
    im = rotate(im, ang, (255, 255, 255)); h = rotate(h, ang, 0); v = rotate(v, ang, 0)
    a, b, score, margin = comb_x(v)
    X0 = a * TX + b
    def rows(top, bot):
        Y0 = top + np.arange(10) * (bot - top) / 9
        Yc = np.zeros((12, 10)); hy = []
        for k in range(12):
            xa, xb = int(X0[2 * k]) + 3, int(X0[2 * k + 2]) - 3
            Yc[k], ht = snap(h[:, xa:xb].sum(1).astype(float) / 255, Y0, 6, 0.5 * (xb - xa)); hy.append(ht.mean())
        return Y0, Yc, float(np.mean(hy))

    top, bot, wscore = row_window(v, h, X0, a)
    Y0, Yc, hy = rows(top, bot)
    if hy < 0.6:                       # 가로선이 거의 안 맞음 = 사진이 세로로 늘거나 줄어 줄 간격이 다르다 → 넓은 간격 범위로 다시 (2026-10-09)
        t2, b2, _ = row_window(v, h, X0, a, spacing=(0.85, 1.20))
        y2, c2, hy2 = rows(t2, b2)
        if hy2 >= hy + 0.1:
            top, bot, Y0, Yc, hy = t2, b2, y2, c2, hy2
    Xr = np.zeros((9, 25)); hx = []
    for k in range(9):
        ya, yb = int(Y0[k]) + 4, int(Y0[k + 1]) - 4
        Xr[k], ht = snap(v[ya:yb].sum(0).astype(float) / 255, X0, 4, 0.5 * (yb - ya)); hx.append(ht.mean())
    return im, dict(angle=ang, a=a, b=b, score=score, margin=margin, top=top, bot=bot,
                    n_rows=int(round((bot - top) / (ROW_H * a))), Xr=Xr, Yc=Yc, hx=float(np.mean(hx)), hy=hy)


def strip_box(g: dict, k: int, r: int) -> tuple[int, int, int, int]:
    """k: 0..11 이닝 칸, r: 0..8 타순 줄 → 투구 표시 띠 (x0, y0, x1, y1), 선 안쪽."""
    xl, xs = g["Xr"][r][2 * k], g["Xr"][r][2 * k + 1]
    yt, yb = g["Yc"][k][r], g["Yc"][k][r + 1]
    return int(round(xl)) + 2, int(round(yt)) + 2, int(round(xs)) - 1, int(round(yb)) - 2


# ---------- 띠 → 투구 표시 ----------

def ink_mask(im: np.ndarray) -> np.ndarray:
    """손글씨 잉크: 어두운 화소 − 인쇄선(1px 두껍게) − 빨간 펜(투수 교체 선)."""
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    ink = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 25, 18)
    h, v = line_masks(im)
    lines = cv2.dilate(cv2.max(h, v), np.ones((3, 3), np.uint8))
    b, gg, r = [im[..., i].astype(int) for i in range(3)]
    red = (r > 110) & (r > gg + 45) & (r > b + 45)
    ink[(lines > 0) | red] = 0
    return ink


def split_stack(m: dict) -> list[dict]:
    """위아래로 맞닿은 표시를 가는 이음매(행 잉크 1px 이하)에서 자른다. 양쪽 모두 굵은 행(3px 이상)이 있을 때만."""
    mk = m["mask"]; prof = mk.sum(1)
    for y in range(3, len(prof) - 3):
        if prof[y] <= 1 and prof[:y].max() >= 3 and prof[y + 1:].max() >= 3:
            res = []
            for part, oy in ((mk[:y], 0), (mk[y + 1:], y + 1)):
                ys, xs = np.nonzero(part)
                if len(ys) == 0:
                    continue
                y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
                res += split_stack(dict(m, x=m["x"] + x0, y=m["y"] + oy + y0, w=x1 - x0, h=y1 - y0, a=int(part.sum()), mask=part[y0:y1, x0:x1]))
            return res
    return [m]


def cell_marks(ink: np.ndarray, box: tuple[int, int, int, int], min_area: int = 3) -> list[dict]:
    """띠 칸 하나의 투구 표시들 (위에서 아래 순). x, y는 띠 칸 안 좌표, mask는 표시 모양."""
    x0, y0, x1, y1 = box
    n, lab, st, cen = cv2.connectedComponentsWithStats(np.ascontiguousarray(ink[y0:y1, x0:x1]), 8)
    comps = sorted((dict(x=int(st[i, 0]), y=int(st[i, 1]), w=int(st[i, 2]), h=int(st[i, 3]), a=int(st[i, 4]), ids=[i])
                    for i in range(1, n) if st[i, 4] >= min_area), key=lambda c: c["y"])
    marks: list[dict] = []
    for c in comps:                                     # 옆으로 나란한 조각만 합친다 (끊긴 동그라미). 같은 줄로 쌓인 획은 따로
        if marks:
            m = marks[-1]
            ov = min(m["y"] + m["h"], c["y"] + c["h"]) - max(m["y"], c["y"])
            ox = min(m["x"] + m["w"], c["x"] + c["w"]) - max(m["x"], c["x"])
            if ov > 0.6 * min(m["h"], c["h"]) and ox < 0.3 * min(m["w"], c["w"]):
                nx0, ny0 = min(m["x"], c["x"]), min(m["y"], c["y"])
                nx1, ny1 = max(m["x"] + m["w"], c["x"] + c["w"]), max(m["y"] + m["h"], c["y"] + c["h"])
                m.update(x=nx0, y=ny0, w=nx1 - nx0, h=ny1 - ny0, a=m["a"] + c["a"], ids=m["ids"] + c["ids"])
                continue
        marks.append(dict(c))
    for m in marks:
        m["mask"] = np.isin(lab[m["y"]:m["y"] + m["h"], m["x"]:m["x"] + m["w"]], m["ids"]).astype(np.uint8)
    out = []
    for m in marks:
        out += split_stack(m)
    return out


def keep(m: dict) -> bool:
    """티끌(4px 미만)과 세로선 찌꺼기를 뺀다."""
    if m["a"] < 4:
        return False
    return not (m["w"] <= 2 or (m["w"] <= 3 and m["h"] >= 4 * m["w"]))


def keep_relative(areas: pd.Series, frac: float = 0.25) -> pd.Series:
    """기록지 안에서 상대 크기로 티끌 거르기: 면적이 그 기록지 표시 면적 중앙값의 frac 미만이면 잡음."""
    return areas >= frac * float(np.median(areas))


def shape_features(m: dict) -> dict:
    mk = m["mask"]
    h, w = mk.shape
    ys, xs = np.nonzero(mk)
    a = len(ys)
    cov = np.cov(np.vstack([xs, ys])) if a > 2 else np.eye(2)
    ev = np.sort(np.linalg.eigvalsh(cov + 1e-6 * np.eye(2)))
    pad = np.pad(mk, 1)
    cnts, hier = cv2.findContours(pad, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    holes = int(sum(1 for i in range(len(cnts)) if hier is not None and hier[0][i][3] >= 0))
    ff = cv2.morphologyEx(pad, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)).copy()
    cv2.floodFill(ff, None, (0, 0), 1)
    hull = cv2.convexHull(np.column_stack([xs, ys]).astype(np.int32)) if a > 2 else None
    side = max(h, w)
    sq = np.zeros((side, side), np.float32); sq[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = mk
    return dict(w=w, h=h, area=a, fill=a / (w * h), elong=float(np.sqrt(ev[1] / ev[0])),
                ang=float(np.degrees(0.5 * np.arctan2(2 * cov[0, 1], cov[0, 0] - cov[1, 1]))), holes=holes,
                enclosed=int((ff == 0).sum()), solidity=float(a / max(1.0, cv2.contourArea(hull))) if hull is not None else 1.0,
                aspect=h / w, pix=cv2.resize(sq, (12, 12), interpolation=cv2.INTER_AREA).ravel())


def center_crop(gray: np.ndarray, cy: int, cx: int) -> np.ndarray:
    """표시 가운데 24x24 회색 그림 (가장자리는 복제)."""
    return cv2.copyMakeBorder(gray, 12, 12, 12, 12, cv2.BORDER_REPLICATE)[cy:cy + 24, cx:cx + 24].copy()


# ---------- 칸 ↔ 공식 타석 ----------

def cells_for(pas: list[dict]) -> list[tuple[int, int] | None]:
    """기록원이 쓰는 칸 (열, 타순): 이닝마다 새 열, 같은 이닝에 같은 타순이 다시 오면(타자 일순) 다음 열. 승부치기 주자는 칸이 없다."""
    col, cur, used, out = 0, None, set(), []
    for p in pas:
        if p["result"] == "승부주자":
            out.append(None)
            continue
        if p["inning"] != cur:
            col += 1; cur = p["inning"]; used = set()
        if p["slot"] in used:
            col += 1; used = set()
        used.add(p["slot"]); out.append((col, p["slot"]))
    return out


def match_team(occupied: set, team_pas: dict[str, list[dict]]) -> list[tuple[float, str]]:
    """기록지의 표시가 있는 칸 무늬와 팀별 기대 칸의 겹침(자카드)으로 타격 팀을 고른다. 높은 순."""
    out = []
    for team, pas in team_pas.items():
        exp = {c for c in cells_for(pas) if c}
        out.append((len(exp & occupied) / max(1, len(exp | occupied)), team))
    return sorted(out, reverse=True)


# ---------- 볼 판정 입력 ----------

def shape_matrix(df: pd.DataFrame) -> np.ndarray:
    """모양만 쓰는 볼 판정 입력 (2026-10-08, 2차 모형): 모양 특징 12개 + 12x12 모양. 자른 조각과 합성 조각에도 같은 뜻을 갖는다."""
    return np.hstack([df[FEATURES].to_numpy(float), np.vstack(df["pix"].to_numpy()).astype(float)])


def ball_matrix(df: pd.DataFrame) -> np.ndarray:
    """분류기 입력: 모양 특징 12개(hr·wr = 기록지 안 중앙값 대비) + 12x12 모양 + 가운데 12x12 회색."""
    pix = np.vstack(df["pix"].to_numpy()).astype(float)
    crop = np.vstack([np.asarray(c, np.float32).reshape(24, 24)[6:18, 6:18].ravel() / 255 for c in df["crop"]])
    return np.hstack([df[FEATURES].to_numpy(float), pix, crop])


# ---------- 등판 단위: 검산·볼 비율·평소 비교 ----------

def outing_table(marks: pd.DataFrame, official: pd.DataFrame, tol: float = 0.15) -> pd.DataFrame:
    """등판(경기·팀·등번호)마다 읽은 표시 수·볼 수와 공식 투구 수. 표시 수가 공식 투구 수와 tol 넘게 다르면 볼 비율을 비운다."""
    keys = ["game_idx", "team", "number"]
    got = marks.groupby(keys).agg(marks=("ball", "size"), balls=("ball", "sum")).reset_index()
    o = official[keys + ["pitches"]].merge(got, on=keys, how="left").fillna({"marks": 0, "balls": 0})
    o["gate"] = (o["pitches"] > 0) & ((o["marks"] / o["pitches"].where(o["pitches"] > 0) - 1).abs() <= tol)
    o["ball_pct"] = np.where(o["gate"], o["balls"] / o["marks"].where(o["marks"] > 0), np.nan)
    return o


def implied_pitches(marks: pd.DataFrame, inplay: set) -> pd.DataFrame:
    """타석 결과가 정해 주는 마지막 공 중 띠에 안 그린 것을 채운다 (2026-10-08). 기록원이 4구의 넷째 볼, 삼진의 셋째 스트라이크,
    인플레이의 타격 공을 결과 기호로 대신하고 띠에는 안 그리는 경우가 있다 — 숫자 줄 이닝 투구 수와 맞춰 보면 그런 타석이 있는 이닝만 1구씩 모자랐다.
    - 4구(고의 아님): 읽은 볼이 4개보다 적으면 4개까지 볼
    - 삼진: 마지막 표시가 볼이거나, 볼 아닌 표시가 2개 이하면 스트라이크 1
    - 인플레이: 마지막 표시가 볼이면 타격(스트라이크) 1
    반환: 덧붙일 줄 — 그 타석 줄의 타석 단위 열을 그대로 쓰고 idx = 그 타석 마지막 + 1부터, k = 0, filled = True."""
    if len(marks) == 0:
        return marks.assign(filled=pd.Series(dtype=bool))
    m = marks.sort_values(["sheet", "pa", "idx", "piece"])
    g = m.groupby(["sheet", "pa"], sort=False)
    pa = g.agg(n=("ball", "size"), balls=("ball", "sum"), last=("ball", "last"), last_idx=("idx", "max"))
    first = g.head(1).set_index(["sheet", "pa"])
    cat, ibb = first["cat"].reindex(pa.index), first["ibb"].reindex(pa.index).fillna(False).astype(bool)
    add_b = np.where((cat == "BB") & ~ibb, np.clip(4 - pa["balls"], 0, 4), 0)
    add_s = (((cat == "K") & ((pa["last"] == 1) | (pa["n"] - pa["balls"] <= 2))) | (cat.isin(inplay) & (pa["last"] == 1))).astype(int).to_numpy()
    shape_cols = [c for c in m.columns if c not in ("sheet", "pa", "idx", "piece", "k", "ball", "p_ball")]
    rows = []
    for (key, b, s), last_idx in zip(zip(pa.index, add_b, add_s), pa["last_idx"]):
        if not b and not s:
            continue
        base = first.loc[key, shape_cols].to_dict()
        for j, ball in enumerate([1] * int(b) + [0] * int(s)):
            rows.append({**base, "sheet": key[0], "pa": key[1], "idx": int(last_idx) + 1 + j, "piece": 0, "k": 0, "ball": ball, "filled": True})
    cols = [*marks.columns, *(["filled"] if "filled" not in marks.columns else [])]
    out = pd.DataFrame(rows, columns=cols) if rows else marks.iloc[:0].assign(filled=pd.Series(dtype=bool))
    for c in ("w", "h", "area", "fill", "elong", "ang", "holes", "enclosed", "solidity", "aspect", "gap_up", "gap_dn", "hr", "wr"):
        if c in out:
            out[c] = np.nan                                     # 그린 표시가 아니므로 모양 값은 없다
    return out


def usual_flags(o: pd.DataFrame, min_pitches: int = 40, z: float = 2.0, min_history: int = 3) -> pd.DataFrame:
    """'평소보다 볼이 많았던 등판': 검산 통과한 등판 중 투구 수 min_pitches 이상만 판정.
    평소 = 같은 투수의 다른 검산 통과 등판들의 볼 합 ÷ 표시 합 (그 등판은 뺀다, 다른 등판 min_history개 이상).
    (볼 비율 − 평소) ÷ √(평소(1−평소)/읽은 표시 수) ≥ z 이면 표시. 원인은 해석하지 않는다."""
    o = o.copy()
    o["usual"] = np.nan; o["z_ball"] = np.nan; o["ball_flag"] = False
    ok = o["gate"].astype(bool)
    for _, g in o[ok].groupby(["team", "number"]):
        tb, tm = g["balls"].sum(), g["marks"].sum()
        for i, r in g.iterrows():
            if len(g) - 1 < min_history:
                continue
            usual = (tb - r["balls"]) / (tm - r["marks"])
            o.at[i, "usual"] = usual
            if r["pitches"] >= min_pitches and 0 < usual < 1:
                zz = (r["ball_pct"] - usual) / np.sqrt(usual * (1 - usual) / r["marks"])
                o.at[i, "z_ball"] = zz
                o.at[i, "ball_flag"] = bool(zz >= z)
    return o


# ---------- 맞닿은 표시: 개수 세기·자르기 (2026-10-08) ----------
# 같은 기록지의 단독 표시를 위아래로 맞닿게 쌓은 합성 견본으로 '덩어리 = 표시 몇 개'를 가르친다(stack_marks).
# 특징은 모양 + 기록지 보통 표시 대비 크기 + 잉크·회색 농도 세로 단면(맞닿은 줄은 잉크가 옅다).

N_BINS = 16
N_COUNT_FEATURES = 14 + 2 * N_BINS + 144


def _resample(v, n: int = N_BINS) -> np.ndarray:
    v = np.asarray(v, float)
    return np.repeat(v, n) if len(v) == 1 else np.interp(np.linspace(0, len(v) - 1, n), np.arange(len(v)), v)


def _dark_profile(gray: np.ndarray) -> np.ndarray:
    d = (255.0 - gray.astype(float)).mean(1)
    d = d - d.min()
    return d / max(1.0, d.max())


def count_features(mask: np.ndarray, gray: np.ndarray, h0: float, w0: float, a0: float) -> np.ndarray:
    """덩어리 하나의 개수 판정 특징 (길이 N_COUNT_FEATURES). h0·w0·a0 = 그 기록지 표시의 높이·너비·면적 중앙값."""
    f = shape_features(dict(mask=mask))
    ink = mask.sum(1).astype(float); ink /= max(1.0, ink.max())
    ds = np.convolve(_dark_profile(gray), np.ones(3) / 3, "same")
    valleys = sum(1 for i in range(2, len(ds) - 2)
                  if ds[i] < ds[i - 1] and ds[i] <= ds[i + 1] and ds[i] < 0.6 * min(ds[:i].max(), ds[i + 1:].max()))
    h, w = mask.shape
    base = [f["w"], f["h"], f["area"], f["fill"], f["elong"], f["ang"], f["holes"], f["enclosed"], f["solidity"], f["aspect"],
            h / h0, w / w0, f["area"] / a0, valleys]
    return np.r_[base, _resample(ink), _resample(_dark_profile(gray)), f["pix"]]


def stack_marks(parts: list[dict], rng) -> tuple[np.ndarray, np.ndarray] | None:
    """단독 표시들(mask·gray)을 위아래로 맞닿게 쌓은 합성 덩어리. 겹침 0~2px(+필요하면 더), 좌우 ±1px. 한 덩어리가 안 되면 None."""
    hs = [p["mask"].shape[0] for p in parts]
    for extra in range(4):
        ov = [min(int(rng.integers(0, 3)) + extra, hs[j] - 1, hs[j + 1] - 1) for j in range(len(parts) - 1)]   # 겹침 < 두 표시의 높이 (넘치지 않게)
        W = max(p["mask"].shape[1] for p in parts) + 2
        H = sum(p["mask"].shape[0] for p in parts) - sum(ov)
        mk = np.zeros((H, W), np.uint8); gp = np.full((H, W), 255, np.uint8)
        y = 0
        for j, p in enumerate(parts):
            h, w = p["mask"].shape
            x = min(max(0, (W - w) // 2 + int(rng.integers(-1, 2))), W - w)
            mk[y:y + h, x:x + w] |= p["mask"]
            gp[y:y + h, x:x + w] = np.minimum(gp[y:y + h, x:x + w], p["gray"])
            if j < len(ov):
                y += h - ov[j]
        if cv2.connectedComponents(mk, connectivity=8)[0] == 2:
            ys, xs = np.nonzero(mk)
            sl = (slice(ys.min(), ys.max() + 1), slice(xs.min(), xs.max() + 1))
            return mk[sl], gp[sl]
    return None


def split_marks(mask: np.ndarray, gray: np.ndarray, k: int) -> list[dict]:
    """덩어리를 위아래 k조각으로 자른다: 잉크·회색 농도가 가장 옅은 줄을, 조각 높이가 고르게(평균의 절반 이상) 되도록 고른다.
    조각마다 mask(잉크 있는 범위로 자름)와 덩어리 안 위치 y·x."""
    H = mask.shape[0]
    if k <= 1 or H < 2 * k:
        return [dict(mask=mask, y=0, x=0)]
    cost = _dark_profile(gray) + mask.sum(1) / max(1.0, mask.sum(1).max())
    minh = max(2, int(0.5 * H / k))
    best = None
    if k == 2:
        for r in range(minh, H - minh + 1):
            c = cost[r] + 0.5 * abs(r - H / 2) / H
            if best is None or c < best[0]:
                best = (c, [r])
    else:
        for r1 in range(minh, H - 2 * minh + 1):
            for r2 in range(r1 + minh, H - minh + 1):
                c = cost[r1] + cost[r2] + 0.5 * (abs(r1 - H / 3) + abs(r2 - 2 * H / 3)) / H
                if best is None or c < best[0]:
                    best = (c, [r1, r2])
    cuts = [0] + best[1] + [H]
    pieces = []
    for a, b in zip(cuts[:-1], cuts[1:]):
        part = mask[a:b]
        ys, xs = np.nonzero(part)
        if len(ys) == 0:
            continue
        pieces.append(dict(mask=part[ys.min():ys.max() + 1, xs.min():xs.max() + 1], y=a + int(ys.min()), x=int(xs.min())))
    return pieces


def holdout_split(game_ids, pilot: set, seed: int = 2025) -> dict:
    """경기 나누기: 시범 경기는 'pilot', 나머지는 시드로 섞어 절반 'test'(학습에 쓰지 않는 시험용), 절반 'label'(2차 학습용)."""
    rest = np.array(sorted(set(int(g) for g in game_ids) - set(pilot)))
    test = set(np.random.default_rng(seed).permutation(rest)[: len(rest) // 2].tolist())
    return {int(g): ("pilot" if g in pilot else "test" if g in test else "label") for g in game_ids}
