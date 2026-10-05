"""피치시그널 핵심 통계 함수 (참조 구현).

이 파일의 함수는 결과 전체의 정확성을 좌우한다.
- 이 파일은 임의로 수정하지 않는다 (저장소 규칙 4).
- 수정이 꼭 필요하면 먼저 tests/test_stats_core.py에 실패하는 테스트를 추가하고,
  수정 이유를 설명한 뒤 승인을 받는다.

용어
- outing(등판): 한 투수가 한 경기에서 던진 주력 패스트볼 투구들의 묶음
- 특징 행렬: 투구 수 n × 특징 수 p 배열. 값은 scale_features()로 단위를 없앤 값
- Σ_w: 등판 안 투구별 잡음 공분산, Σ_b: 날마다 달라지는 등판 간 변동 공분산
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


# ---------------------------------------------------------------------------
# 0. 입력 정리
# ---------------------------------------------------------------------------
def as_2d(o) -> np.ndarray:
    """등판 하나의 투구 배열을 (투구 수, 특징 수) 2차원으로 바꾸고 결측을 검사한다.

    특징이 하나(p = 1, 예: B4·KBO 구속)면 1차원 배열을 (n, 1)로 바꾼다.
    결측(NaN·inf)이 있으면 오류를 낸다 — 결측 투구는 호출하기 전에 빼야 한다.
    """
    a = np.asarray(o, dtype=float)
    if a.ndim == 1:
        a = a[:, None]
    if not np.isfinite(a).all():
        raise ValueError("투구 배열에 결측(NaN/inf)이 있습니다. 결측 투구를 먼저 빼세요.")
    return a


# ---------------------------------------------------------------------------
# 1. 단위 없애기
# ---------------------------------------------------------------------------
def scale_factors(baseline_outings: list[np.ndarray]) -> np.ndarray:
    """기준선 등판들의 '등판 안 투구별 표준편차'(합동)를 특징별로 돌려준다.

    특징마다 단위(mph, ft, 도)가 달라 고윳값 하한 등을 공정하게 적용하려면
    먼저 이 값으로 나눠 단위를 없앤다.
    """
    baseline_outings = [as_2d(o) for o in baseline_outings]
    multi = [o for o in baseline_outings if len(o) > 1]
    if not multi:
        raise ValueError("투구가 2개 이상인 기준선 등판이 없습니다.")
    num = sum(((o - o.mean(0)) ** 2).sum(0) for o in multi)
    den = sum(len(o) - 1 for o in multi)
    sd = np.sqrt(num / den)
    sd[sd == 0] = 1.0
    return sd


# ---------------------------------------------------------------------------
# 2. 기준선 (Phase I)
# ---------------------------------------------------------------------------
@dataclass
class Baseline:
    mu: np.ndarray      # 등판 평균의 평균 (p,)
    Sb: np.ndarray      # 등판 간 변동 공분산 (p, p)
    Sw: np.ndarray      # 투구별 잡음 공분산 (p, p)
    n_outings: int      # 기준선에 쓰인 등판 수


def phase1(outings: list[np.ndarray], floor: float = 0.01) -> Baseline:
    """기준선 등판들로 μ, Σ_b, Σ_w를 추정한다.

    Σ_w = 등판별 표본공분산을 (n_i - 1)로 가중 평균
    Σ_b = Cov(등판 평균) - mean(1/n_i) * Σ_w   (적률 추정)
    Σ_b가 양정치가 아니면 고윳값을 floor 이상으로 올린다.
    """
    if len(outings) < 3:
        raise ValueError("기준선 등판이 3개 미만입니다.")
    outings = [as_2d(o) for o in outings]
    p = outings[0].shape[1]
    xbar = np.array([o.mean(0) for o in outings])
    n = np.array([len(o) for o in outings], dtype=float)
    multi = [o for o in outings if len(o) > 1]
    Sw = sum((len(o) - 1) * np.atleast_2d(np.cov(o, rowvar=False)) for o in multi)
    Sw = Sw / sum(len(o) - 1 for o in multi)
    Sb = np.atleast_2d(np.cov(xbar, rowvar=False)) - np.mean(1.0 / n) * Sw
    w, V = np.linalg.eigh((Sb + Sb.T) / 2)
    Sb = V @ np.diag(np.maximum(w, floor)) @ V.T
    return Baseline(mu=xbar.mean(0), Sb=Sb, Sw=Sw.reshape(p, p), n_outings=len(outings))


def phase1_refined(outings: list[np.ndarray], ucl: float, floor: float = 0.01,
                   rounds: int = 1) -> tuple[Baseline, list[int]]:
    """기준선 안에서 T²가 ucl을 넘는 등판을 빼고 다시 추정하기를 rounds번 반복한다.

    각 등판의 T²는 그 등판을 뺀 나머지로 추정한 기준선에 대해 계산한다(leave-one-out).
    이상 등판이 공분산을 부풀려 자기 자신을 가리는 '가림 효과'를 막기 위해서다.
    반환: (최종 기준선, 제외된 등판의 원래 인덱스 목록)
    """
    outings = [as_2d(o) for o in outings]
    keep = list(range(len(outings)))
    removed: list[int] = []
    base = phase1(outings, floor)
    for _ in range(rounds):
        if len(keep) < 4:
            break
        t2 = []
        for i in keep:
            loo = phase1([outings[j] for j in keep if j != i], floor)
            t2.append(t2_stat(outing_u(outings[i].mean(0), len(outings[i]), loo)))
        drop = [i for i, v in zip(keep, t2) if v > ucl]
        if not drop or len(keep) - len(drop) < 3:
            break
        removed += drop
        keep = [i for i in keep if i not in drop]
        base = phase1([outings[i] for i in keep], floor)
    return base, removed


# ---------------------------------------------------------------------------
# 3. 가변 표본 표준화와 통계량 (Phase II)
# ---------------------------------------------------------------------------
def outing_u(xbar: np.ndarray, n: int, base: Baseline) -> np.ndarray:
    """투구 수 n에 맞춰 등판 평균을 표준화한다.

    C = Σ_b + Σ_w / n,   u = L^T (x̄ - μ)  (C^{-1} = L L^T)
    정상 상태라면 u ~ N(0, I) 이며, 이는 투구 수와 무관하다.
    """
    x = np.atleast_1d(np.asarray(xbar, dtype=float))
    if not np.isfinite(x).all() or n < 1:
        raise ValueError("등판 평균에 결측이 있거나 투구 수가 0입니다.")
    C = base.Sb + base.Sw / float(n)
    L = np.linalg.cholesky(np.linalg.inv(C))
    return L.T @ (x - base.mu)


def t2_stat(u: np.ndarray) -> float:
    """Hotelling T² (표준화된 u의 제곱합)."""
    return float(np.dot(u, u))


def t2_ucl(p: int, alpha: float) -> float:
    """T² 이론 관리한계 χ²_{p, 1-α}. 실제 사용 전 개발셋으로 보정한다."""
    return float(stats.chi2.ppf(1 - alpha, p))


@dataclass
class MonitorResult:
    q: np.ndarray        # 등판별 MEWMA 통계량
    t2: np.ndarray       # 등판별 T²
    alarm: np.ndarray    # 등판별 경보 여부 (bool)


def monitor(U: np.ndarray, h: float, ucl: float, lam: float,
            reset_after_alarm: bool = True) -> MonitorResult:
    """등판 순서대로 쌓은 u (T × p)에 T²와 MEWMA를 적용한다.

    경보 규칙: T²_t > ucl 또는 Q_t > h
    Q_t = (2-λ)/λ · z_tᵀ z_t,  z_t = λ u_t + (1-λ) z_{t-1}
    reset_after_alarm=True면 경보 직후 z를 0으로 되돌린다
    (경보 하나를 한 번의 사건으로 세고, 오경보율 ≈ 100/ARL0가 되도록).
    """
    U = np.asarray(U, dtype=float)
    if U.ndim == 1:
        U = U[:, None]          # p = 1 (등판 수 T개의 1차원 배열)
    if not np.isfinite(U).all():
        raise ValueError("u에 결측이 있습니다. 결측 등판은 감시에서 빼고 넘기세요 (NaN이 들어가면 이후 경보가 모두 사라짐).")
    T, p = U.shape
    c = (2 - lam) / lam
    z = np.zeros(p)
    q = np.zeros(T)
    t2 = np.zeros(T)
    alarm = np.zeros(T, dtype=bool)
    for t in range(T):
        z = lam * U[t] + (1 - lam) * z
        q[t] = c * float(z @ z)
        t2[t] = float(U[t] @ U[t])
        alarm[t] = (q[t] > h) or (t2[t] > ucl)
        if alarm[t] and reset_after_alarm:
            z = np.zeros(p)
    return MonitorResult(q=q, t2=t2, alarm=alarm)


# ---------------------------------------------------------------------------
# 4. 오경보 설계 (ARL)
# ---------------------------------------------------------------------------
def _run_lengths(X: np.ndarray, h: float, ucl: float, lam: float) -> np.ndarray:
    """X: (R, T, p) 표준정규 시퀀스. 각 시퀀스의 첫 경보까지 등판 수를 돌려준다."""
    R, T, p = X.shape
    c = (2 - lam) / lam
    z = np.zeros((R, p))
    rl = np.full(R, T, dtype=float)
    alive = np.ones(R, dtype=bool)
    for t in range(T):
        x = X[:, t, :]
        z = lam * x + (1 - lam) * z
        q = c * np.einsum("ij,ij->i", z, z)
        t2 = np.einsum("ij,ij->i", x, x)
        hit = alive & ((q > h) | (t2 > ucl))
        rl[hit] = t + 1
        alive &= ~hit
        if not alive.any():
            break
    return rl


def arl0(h: float, p: int, lam: float, ucl: float, n_sim: int = 3000,
         max_len: int = 1500, seed: int = 0) -> float:
    """정상 상태 평균 런 길이(ARL0)를 시뮬레이션으로 계산한다."""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_sim, max_len, p))
    return float(_run_lengths(X, h, ucl, lam).mean())


def calibrate_h(p: int, lam: float, ucl: float, target: float = 100.0,
                n_sim: int = 3000, max_len: int = 1500, seed: int = 0,
                lo: float = 1.0, hi: float = 40.0, iters: int = 30) -> float:
    """ARL0가 target이 되는 MEWMA 한계 h를 이분법으로 찾는다 (공통 난수 사용)."""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_sim, max_len, p))
    f = lambda h: _run_lengths(X, h, ucl, lam).mean()
    if f(hi) < target:
        raise ValueError("hi를 더 크게 잡아야 합니다 (T² 한계 때문에 목표 ARL0에 못 미칠 수 있음).")
    for _ in range(iters):
        mid = (lo + hi) / 2
        if f(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def arl1(h: float, p: int, lam: float, ucl: float, shift: np.ndarray,
         n_sim: int = 3000, max_len: int = 1500, seed: int = 1) -> float:
    """표준화 단위 평균 이동 shift (p,)가 처음부터 있을 때의 평균 탐지 등판 수."""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n_sim, max_len, p)) + np.asarray(shift)[None, None, :]
    return float(_run_lengths(X, h, ucl, lam).mean())


def empirical_false_alarm_rate(results: list[MonitorResult]) -> float:
    """여러 대조군 투수-시즌의 감시 결과에서 100등판당 경보 수를 계산한다."""
    alarms = sum(int(r.alarm.sum()) for r in results)
    outings = sum(len(r.alarm) for r in results)
    return 100.0 * alarms / outings if outings else float("nan")


# ---------------------------------------------------------------------------
# 5. 투구 수 하한
# ---------------------------------------------------------------------------
def n_min(sigma_w: float, sigma_b: float) -> float:
    """표본 잡음(σ_w²/n)이 등판 간 변동(σ_b²)과 같아지는 투구 수 (σ_w/σ_b)²."""
    if sigma_b <= 0:
        return float("inf")
    return (sigma_w / sigma_b) ** 2
