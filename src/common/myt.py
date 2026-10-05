"""경보 원인 분해 (SPEC 3.10, MYT 분해). 10_myt·08_evaluate가 같이 쓴다.

T² = (x̄ − m)ᵀ C⁻¹ (x̄ − m)를 특징별 몫으로 나눈다. x̄는 등판 평균, m은 예상값, C는 예측 오차의 공분산이며
셋 다 같은 단위(원래 단위)면 된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LABELS = {"velo": "구속", "rel_z": "수직 릴리스", "arm_angle": "팔 각도", "rel_x": "수평 릴리스",
          "extension": "익스텐션", "spin": "회전수", "rel_z_sd": "릴리스 높이 흔들림"}      # 경보 카드에 쓰는 이름


def _t2(d: np.ndarray, cov: np.ndarray, index: np.ndarray) -> float:
    return float(d[index] @ np.linalg.solve(cov[np.ix_(index, index)], d[index]))


def decompose(x: np.ndarray, expected: np.ndarray, cov: np.ndarray, names: list[str]) -> pd.DataFrame:
    """특징별 분해표 (행 = 특징, names 순서).

    z           부호 있는 표준화 이탈 (x̄ − m) ÷ 표준편차
    alone       무조건 항: 그 특징만 봤을 때의 T² (= z²)
    given_rest  조건부 항: 나머지 특징을 모두 알고 봤을 때 남는 이탈
    step        alone이 큰 특징부터 하나씩 더해 갈 때 늘어나는 몫. 모두 더하면 T²
    """
    d = np.asarray(x, dtype=float) - np.asarray(expected, dtype=float)
    precision = np.linalg.inv(cov)
    alone = d ** 2 / np.diag(cov)
    order, step, so_far = np.argsort(-alone, kind="stable"), np.zeros(len(d)), 0.0
    for k in range(len(d)):
        now = _t2(d, cov, order[:k + 1])
        step[order[k]], so_far = now - so_far, now
    return pd.DataFrame({"z": d / np.sqrt(np.diag(cov)), "alone": alone,
                         "given_rest": (precision @ d) ** 2 / np.diag(precision), "step": step}, index=names)


def card(parts: pd.DataFrame, top: int = 2) -> str:
    """경보 카드 문구: 몫(step)이 큰 특징 top개의 부호 있는 표준화 이탈. 예: '수직 릴리스 −1.8σ, 구속 −1.2σ'"""
    largest = parts.sort_values("step", ascending=False, kind="stable").head(top)
    return ", ".join(f"{LABELS[name]} {z:+.1f}σ".replace("-", "−") for name, z in largest["z"].items())


def ewma_vectors(u: np.ndarray, alarm: np.ndarray, lam: float) -> np.ndarray:
    """등판별 EWMA 벡터 z_t (등판 수 × 특징 수). 관리도가 경보를 낸(alarm) 다음 등판은 0에서 다시 시작한다."""
    z, out = np.zeros(u.shape[1]), np.zeros(u.shape)
    for t in range(len(u)):
        z = lam * u[t] + (1 - lam) * z
        out[t] = z
        if alarm[t]:
            z = np.zeros(u.shape[1])
    return out
