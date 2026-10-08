"""기록지 맨 아래 '투구수' 줄 판독: 이닝 칸마다 (그 이닝 투구 수 | 누적)이 손글씨 숫자로 적혀 있다(1회는 누적 하나).

- 숫자 떼기: 이닝 칸 가운데 칸막이로 왼쪽·오른쪽 수를 나눈다. 1회 칸 왼쪽 절반은 인쇄 글자 '투구수'라 오른쪽만 쓴다.
- 맞닿은 숫자: 덩어리를 몇 조각으로 자를지 미리 정하지 않는다. 덩어리마다 1·2·3조각 가설을 모두 만들고(폭 사전 + 숫자 분류 확률),
  수 하나의 값 표 = 가설들 중 최댓값. 읽은 수가 틀렸어도(자릿수까지) 사슬이 지나가도록 모든 값에 바닥 확률을 준다.
- 누적 사슬: 누적 = 앞 누적 + 이닝 투구 수, 마지막 누적 = 상대 투수진 공식 투구 수 합. 동적 계획법으로 가장 그럴듯한 이닝 값들을 고른다.
  숫자 없는 열(타자 일순으로 넘어간 열)은 0구를 허용. 선택으로 그 열의 기록지 표시 수를 사전 정보로, 공식 기록으로 아는 누적(투수 교체가 이닝
  경계인 곳)을 고정점으로 쓴다.
검증(시험용 경기, 2026-10-08): 사람이 읽고 사슬·공식 합으로 검산한 30장 241이닝 중 97.5% 일치, 939장의 투수 교체 경계 누적 92.0% 일치."""
from __future__ import annotations

import itertools

import cv2
import numpy as np

from src.common import scoresheet as ss

MAXV, MAXI = 400, 80                       # 누적·이닝 투구 수 상한
MISSING_LP = float(np.log(0.002))          # 빈 수: 모든 값 같은 낮은 확률
FLOOR_LP = float(np.log(1e-4))             # 읽은 수가 틀렸을 때의 바닥 확률
EMPTY_LP = float(np.log(0.02))             # 숫자 없는 열을 0구로 볼 때
NEG = -1e18
SEG_HI, SEG_LO = 0.3, 0.15                 # 한 조각이 너무 넓을 때·여러 조각이 너무 좁을 때의 폭 벌점 폭
PRIOR = (0.5, -0.08, 0.8, 0.1, 0.05)       # 표시 수 m − 이닝 투구 수 v ~ 라플라스(0.5 − 0.08v, max(0.8, 0.1v)) + 바닥 5%


# ---------- 떼기 ----------

def row_band(im: np.ndarray, g: dict) -> tuple[int, int]:
    """투구수 줄의 위·아래 y: 기준 양식 839~860 (타순 9줄 아래 경계 716 기준), 가까운 가로 인쇄선으로 다듬는다."""
    h, _ = ss.line_masks(im)
    a = g["a"]; bot = float(np.median(g["Yc"][:, 9]))
    y0 = bot + (123 / 60.3) * ss.ROW_H * a; y1 = bot + (144 / 60.3) * ss.ROW_H * a
    x0, x1 = int(g["Xr"][8][0]), int(g["Xr"][8][24])
    prof = h[:, x0:x1].sum(1).astype(float) / 255

    def near(y):
        lo, hi = int(y) - 5, int(y) + 6
        j = lo + int(np.argmax(prof[lo:hi]))
        return j if prof[j] > 0.3 * (x1 - x0) else int(round(y))
    return near(y0), near(y1)


def components(ink: np.ndarray, x0: int, x1: int, y0: int, y1: int) -> list[dict]:
    sub = np.ascontiguousarray(ink[y0 + 2:y1 - 1, x0 + 2:x1 - 1])
    n, lab, st, _ = cv2.connectedComponentsWithStats(sub, 8)
    out = []
    for i in range(1, n):
        x, y, w, h, a = (int(v) for v in st[i])
        if a >= 5:
            out.append(dict(x=x + x0 + 2, y=y, w=w, h=h, a=a, mask=(lab[y:y + h, x:x + w] == i).astype(np.uint8)))
    return out


def extract(im: np.ndarray, g: dict, ink: np.ndarray) -> dict:
    """사진(기울기 바로잡은 것)·격자·잉크 → 이닝 칸 12개의 왼쪽(L)·오른쪽(R) 숫자 덩어리, 보통 숫자 높이·폭."""
    y0, y1 = row_band(im, g)
    raw = []
    for k in range(12):
        x0, x1 = int(g["Xr"][8][2 * k]), int(g["Xr"][8][2 * k + 2])
        raw.append((x0, x1, components(ink, x0, x1, y0, y1)))
    allc = [c for _, _, cs in raw for c in cs]
    if not allc:
        return dict(cols=[], h_med=0.0, w_digit=0.0)
    h_med = float(np.median([c["h"] for c in allc if c["a"] >= 12] or [c["h"] for c in allc]))
    wide = [c["w"] for c in allc if c["h"] >= 0.7 * h_med and c["h"] / max(1, c["w"]) < 2.2 and c["w"] <= 1.3 * c["h"]]   # '1' 빼고 낱자
    w_digit = float(np.median(wide)) if wide else 0.7 * h_med
    cols = []
    for k, (x0, x1, cs) in enumerate(raw):
        cs = sorted([c for c in cs if c["h"] >= 0.4 * h_med], key=lambda c: c["x"])        # 점·인쇄 조각은 빼고 짧은 '1'은 남긴다
        mid = (x0 + x1) / 2
        keep = lambda c: dict(x=c["x"], w=c["w"], h=c["h"], mask=c["mask"])
        L = [keep(c) for c in cs if c["x"] + c["w"] / 2 < mid]
        R = [keep(c) for c in cs if c["x"] + c["w"] / 2 >= mid]
        cols.append(dict(L=[] if k == 0 else L, R=R))
    return dict(cols=cols, h_med=h_med, w_digit=w_digit)


# ---------- 숫자 조각 ----------

def norm16(mask: np.ndarray) -> np.ndarray:
    h, w = mask.shape
    side = max(h, w)
    sq = np.zeros((side, side), np.float32); sq[(side - h) // 2:(side - h) // 2 + h, (side - w) // 2:(side - w) // 2 + w] = mask
    return cv2.resize(sq, (16, 16), interpolation=cv2.INTER_AREA).ravel()


def digit_features(mask: np.ndarray, h_med: float) -> np.ndarray:
    """숫자 하나: 16x16 모양 + 세로/가로 비 + 보통 숫자 높이에 대한 높이 (258)."""
    return np.r_[norm16(mask), mask.shape[0] / max(1, mask.shape[1]), mask.shape[0] / max(1e-6, h_med)].astype(np.float32)


def cut(c: dict, n: int) -> list[np.ndarray] | None:
    """덩어리를 세로 투영이 가장 옅은 열에서 n조각 (고르게 나눈 자리 ±30%). 빈 조각이 생기면 None."""
    if n == 1:
        return [c["mask"]]
    prof = c["mask"].sum(0).astype(float); W = c["w"]; cuts, prev = [], 0
    for j in range(1, n):
        ideal = j * W / n; lo, hi = int(max(prev + 2, ideal - 0.3 * W / n)), int(min(W - 2, ideal + 0.3 * W / n))
        cuts.append(lo + int(np.argmin(prof[lo:hi + 1])) if hi > lo else int(ideal)); prev = cuts[-1]
    out = []
    for a, b in zip([0] + cuts, cuts + [W]):
        m = c["mask"][:, a:b]; ys, xs = np.nonzero(m)
        if len(ys) == 0:
            return None
        out.append(m[ys.min():ys.max() + 1, xs.min():xs.max() + 1])
    return out


def seg_prior(r: float, n: int) -> float:
    """폭 비율 r(덩어리 폭 / 보통 숫자 폭)을 n조각으로: 한 조각이 너무 넓으면(>1.15) 벌점, 2조각 이상인데 조각이 너무 좁으면(<0.75) 더 큰 벌점.
    한 조각(n=1)의 좁음은 벌하지 않는다('1')."""
    q = r / n
    lp = -max(0.0, q - 1.15) ** 2 / (2 * SEG_HI ** 2)
    if n > 1:
        lp -= max(0.0, 0.75 - q) ** 2 / (2 * SEG_LO ** 2)
    return float(lp)


def hypotheses(comps: list[dict], w_digit: float) -> list[tuple[float, list[np.ndarray]]]:
    """수 하나(덩어리들) → [(폭 사전 로그확률, [숫자 mask...])], 숫자 1~3개."""
    if not comps:
        return []
    opts = []
    for c in comps:
        r = c["w"] / max(1e-6, w_digit); o = []
        for n in (1, 2, 3):
            if n > 1 and c["w"] < 2 * n + 2:
                continue
            pcs = cut(c, n)
            if pcs is not None:
                o.append((seg_prior(r, n), pcs))
        opts.append(o)
    out = []
    for combo in itertools.product(*opts):
        pcs = [p for _, ps in combo for p in ps]
        if 1 <= len(pcs) <= 3:
            out.append((sum(lp for lp, _ in combo), pcs))
    return out


# ---------- 값 표·사슬 ----------

def value_table(P: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """수 하나의 숫자 확률 (m×10) → (값들, 로그확률). 두 자리 이상에서 맨 앞 0 금지."""
    L = np.log(np.maximum(P, 1e-6))
    vals = np.zeros(1, int); lp = np.zeros(1)
    for i in range(len(P)):
        vals = (vals[:, None] * 10 + np.arange(10)[None, :]).ravel(); lp = (lp[:, None] + L[i][None, :]).ravel()
    if len(P) > 1:
        lp[vals < 10 ** (len(P) - 1)] = -1e9
    return vals, lp


def number_table(hyps: list[tuple[float, np.ndarray]]) -> np.ndarray:
    """[(폭 사전, 숫자 확률 m×10)] → 0..MAXV 모든 값의 로그확률. 가설이 없으면 '모름'(평평), 있으면 바닥 확률 위에 가설 중 최댓값."""
    if not hyps:
        return np.full(MAXV + 1, MISSING_LP)
    out = np.full(MAXV + 1, FLOOR_LP)
    for lp0, P in hyps:
        v, l = value_table(P); ok = v <= MAXV
        out[v[ok]] = np.maximum(out[v[ok]], l[ok] + lp0)
    return out


def raw_value(hyps: list[tuple[float, np.ndarray]]) -> int | None:
    """가장 그럴듯한 가설을 그대로 읽은 값 (사슬 없이)."""
    if not hyps:
        return None
    sc = [lp0 + np.log(np.maximum(P.max(1), 1e-6)).sum() for lp0, P in hyps]
    P = hyps[int(np.argmax(sc))][1]
    return int("".join(map(str, P.argmax(1))))


def full_proba(clf, F: np.ndarray) -> np.ndarray:
    """분류기 확률을 숫자 0~9 열로 (학습에 없던 숫자는 0)."""
    P = np.zeros((len(F), 10))
    if len(F):
        P[:, clf.classes_] = clf.predict_proba(F)
    return P


def read_tables(row: dict, last: int, proba) -> tuple[list, list]:
    """열 1..last → [(이닝 수 표 | None, 누적 표, 빈 열?)], 그대로 읽은 [(이닝, 누적)]. proba(F) → (n, 10)."""
    hy = []
    for k in range(last):
        c = row["cols"][k] if k < len(row["cols"]) else dict(L=[], R=[])
        hy.append((None if k == 0 else hypotheses(c["L"], row["w_digit"]), hypotheses(c["R"], row["w_digit"])))
    feats = [digit_features(m, row["h_med"]) for a, b in hy for hs in (a, b) if hs for _, pcs in hs for m in pcs]
    P = proba(np.array(feats)) if feats else np.zeros((0, 10))
    pos = 0; tabs, raws = [], []
    for a, b in hy:
        res = []
        for hs in (a, b):
            if hs is None:
                res.append((None, None)); continue
            hp = []
            for lp0, pcs in hs:
                hp.append((lp0, P[pos:pos + len(pcs)])); pos += len(pcs)
            res.append((number_table(hp), raw_value(hp)))
        empty = a is not None and not a and not b
        tabs.append((res[0][0], np.zeros(MAXV + 1) if empty else res[1][0], empty))
        raws.append((res[0][1], res[1][1]))
    return tabs, raws


def mark_prior(m: int | None, lam: float, params=PRIOR) -> np.ndarray:
    """그 열 기록지 표시 수 m → 이닝 투구 수 v(0..MAXI) 로그확률 × lam. 표시 수를 모르면 0."""
    if m is None or not lam:
        return np.zeros(MAXI + 1)
    mu0, mu1, bmin, b1, floor = params
    v = np.arange(MAXI + 1); b = np.maximum(bmin, b1 * v)
    p = np.exp(-np.abs(m - v - (mu0 + mu1 * v)) / b) / (2 * b)
    return lam * np.log(np.maximum((1 - floor) * p + floor / (MAXI + 1), 1e-12))


def chain_decode(tabs: list, total: int, priors: list | None = None, anchors: dict | None = None, lower: dict | None = None) -> list[int] | None:
    """누적 사슬: 열마다 (이닝 수 표 | None(1회), 누적 표, 빈 열?) → 마지막 누적 = total 인 가장 그럴듯한 이닝 값들.
    anchors {열(1부터): 누적}은 고정, lower {열: 최소 투구 수}(그 열에만 있는 이닝의 타석 수)보다 작은 값은 쓰지 않는다."""
    if total > MAXV or not tabs:
        return None
    score = np.full(MAXV + 1, NEG); score[0] = 0.0; back = []
    for k, (ti, tc, empty) in enumerate(tabs):
        inn = (ti[:MAXI + 1].copy() if ti is not None else np.zeros(MAXI + 1)) + (priors[k] if priors is not None else 0.0)
        inn[0] = EMPTY_LP if (empty and k > 0) else NEG
        if lower and lower.get(k + 1):
            inn[:min(MAXI + 1, int(lower[k + 1]))] = NEG
        new = np.full(MAXV + 1, NEG); arg = np.full(MAXV + 1, -1)
        for v in range(MAXI + 1):
            if inn[v] <= NEG / 2:
                continue
            cand = np.full(MAXV + 1, NEG); cand[v:] = score[:MAXV + 1 - v] + inn[v]
            upd = cand > new; new[upd] = cand[upd]; arg[upd] = v
        score = new + tc
        if anchors and (k + 1) in anchors:
            keep = int(anchors[k + 1]); fixed = np.full(MAXV + 1, NEG)
            if 0 <= keep <= MAXV:
                fixed[keep] = score[keep]
            score = fixed
        back.append(arg)
    if score[total] <= NEG / 2:
        return None
    inns = []; c = total
    for k in range(len(tabs) - 1, -1, -1):
        v = int(back[k][c]); inns.append(v); c -= v
    return inns[::-1]


def decode(row: dict, total: int, last: int, proba, marks: dict | None = None, lam: float = 0.0, anchors: dict | None = None,
           lower: dict | None = None) -> dict | None:
    """기록지 하나의 투구수 줄 → {inns: 열마다 이닝 투구 수, fixed: 그대로 읽은 값에서 고친 수의 개수, raws}. marks {열: 표시 수}."""
    if not row.get("cols") or last < 1 or total > MAXV:
        return None
    tabs, raws = read_tables(row, last, proba)
    priors = [mark_prior(None if marks is None else marks.get(k + 1), lam) for k in range(last)] if lam else None
    inns = chain_decode(tabs, total, priors, anchors, lower)
    if inns is None:
        return None
    cums = np.cumsum(inns)
    fixed = sum(int(ri != v) for (ri, _), v in zip(raws[1:], inns[1:]) if ri is not None) + sum(int(rc != cv) for (_, rc), cv in zip(raws, cums) if rc is not None)
    return dict(inns=inns, fixed=fixed, raws=raws)


# ---------- 공식 기록과 맞추기 ----------

def boundaries(pitchers_by_col: dict, official: dict, last: int) -> list[tuple[int, int]]:
    """투수 교체가 열(이닝) 경계에서 일어난 곳: (열 c, 앞 투수들 공식 투구 수 합). 마지막 열(전체 합)은 뺀다.
    pitchers_by_col {열: {등번호}}, official {등번호: 공식 투구 수}."""
    out = []
    for c in range(1, last):
        before = {p for cc, ps in pitchers_by_col.items() if cc <= c for p in ps}
        after = {p for cc, ps in pitchers_by_col.items() if cc > c for p in ps}
        if before and after and not (before & after) and before <= set(official):
            out.append((c, int(sum(official[p] for p in before))))
    return out


def outing_innings(number: int, official: int, T: dict, pitchers: dict, marks, tol: tuple[float, float]) -> list[dict]:
    """한 투수 등판의 이닝별 투구 수와 볼·스트라이크(추정).
    T {이닝: 숫자 줄 이닝 투구 수}, pitchers {이닝: 그 이닝에 던진 등번호들}, marks = 그 기록지 표시(조각) 표 (inning·number·ball).
    - 혼자 던진 이닝 = 숫자 줄 값. 교체 이닝 몫 = 공식 투구 수 − 혼자 던진 이닝 합 (교체 이닝이 둘이면 그 투수 표시 수 비율로 나눔).
      이 몫이 0~교체 이닝 합 밖이거나, 교체 이닝 없이 합이 공식과 다르면 숫자 줄과 공식 기록이 어긋난 것 → 빈 목록.
    - 볼 = 그 이닝 그 투수 표시의 볼 비율 × 투구 수(반올림), 스트라이크 = 나머지. 그 이닝 전체 표시 수가 숫자 줄과
      max(tol[0], tol[1]×투구 수)보다 많이 다르면 볼·스트라이크는 비운다(None)."""
    inns = sorted(i for i, ps in pitchers.items() if number in ps)
    if not inns or any(i not in T for i in inns):
        return []
    whole = [i for i in inns if pitchers[i] == {number}]
    shared = [i for i in inns if i not in whole]
    pitch = {i: int(T[i]) for i in whole}
    rest = int(official) - sum(pitch.values())
    if not shared:
        if rest != 0:
            return []
    else:
        if not 0 <= rest <= sum(int(T[i]) for i in shared):
            return []
        mine = [int(((marks["inning"] == i) & (marks["number"] == number)).sum()) for i in shared]
        w = np.array(mine, float) / sum(mine) if sum(mine) else np.full(len(shared), 1 / len(shared))
        raw = rest * w; base = np.floor(raw).astype(int)
        for j in np.argsort(-(raw - base))[: rest - int(base.sum())]:
            base[j] += 1
        pitch.update({i: int(v) for i, v in zip(shared, base)})
    if any(v < 1 for v in pitch.values()):                       # 던진 이닝에 공이 없을 수 없다 → 숫자 줄을 믿지 않는다
        return []
    out = []
    for i in inns:
        m_all = marks[marks["inning"] == i]
        m_mine = m_all[m_all["number"] == number]
        ok = len(m_mine) > 0 and abs(len(m_all) - T[i]) <= max(tol[0], tol[1] * T[i])
        balls = int(np.floor(pitch[i] * m_mine["ball"].sum() / len(m_mine) + 0.5)) if ok else None
        out.append(dict(inning=int(i), pitches=pitch[i], shared=i in shared, marks=int(len(m_mine)), balls=balls,
                        strikes=pitch[i] - balls if ok else None))
    return out
