"""짧은 등판 처리 방식 비교 시뮬레이션 (실행기획서 3.8절, 단계 2.4).

① 분산 하나로 모든 등판을 같게 처리 vs ② 가변 표본 표준화(stats_core와 같은 원리)를
같은 ARL0(기본 100)로 맞춘 뒤 비교한다. 구속 1개 특징.

사용 예:
    python tools/sim_short_outings.py --sw 1.0 --sb 0.5 --out reports/tables/sim_short_outings.csv
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy import stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sw", type=float, default=1.0, help="등판 안 투구별 표준편차 σ_w")
    ap.add_argument("--sb", type=float, default=0.5, help="등판 간 표준편차 σ_b")
    ap.add_argument("--mean-n", type=float, default=8, help="불펜 등판당 평균 패스트볼 수")
    ap.add_argument("--lam", type=float, default=0.2)
    ap.add_argument("--arl0", type=float, default=100)
    ap.add_argument("--shift", type=float, default=0.5, help="탐지 시나리오의 평균 이동(원래 단위)")
    ap.add_argument("--reps", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)

    def draw_n(size, short=False):
        if short:
            return rng.integers(3, 6, size)
        return np.clip(rng.poisson(a.mean_n, size), 3, 16)

    var = lambda n: a.sb ** 2 + a.sw ** 2 / n
    pool = var(draw_n(200000)).mean()

    def stat_path(xbar, n, method):
        s = np.sqrt(pool) if method == 1 else np.sqrt(var(n))
        u = xbar / s
        z = np.zeros(u.shape[0]); q = np.zeros_like(u)
        for t in range(u.shape[1]):
            z = a.lam * u[:, t] + (1 - a.lam) * z
            q[:, t] = z ** 2 / (a.lam / (2 - a.lam))
        return q

    def rl(q, h):
        hit = q > h
        return np.where(hit.any(1), hit.argmax(1) + 1, q.shape[1])

    rows = []
    c = stats.chi2.ppf(0.99, 1)
    for n in [3, 5, 8, 12, 16]:
        rows.append({"항목": f"등판 하나 오경보율 ({n}구)", "분산 하나": stats.chi2.sf(c * pool / var(n), 1),
                     "가변 표본": 0.01})
    T = 400
    n0 = draw_n((a.reps, T)); x0 = rng.normal(0, np.sqrt(var(n0)))
    hs = {}
    for m in (1, 2):
        q = stat_path(x0, n0, m)
        lo, hi = 1.0, 20.0
        for _ in range(40):
            h = (lo + hi) / 2
            if rl(q, h).mean() < a.arl0:
                lo = h
            else:
                hi = h
        hs[m] = h
    scen = {
        "평소 그대로, 10등판 안 경보": (draw_n((a.reps, 60)), 0.0),
        "기용만 짧아짐, 10등판 안 경보": (draw_n((a.reps, 60), short=True), 0.0),
        f"구속 {a.shift} 하락, 10등판 안 탐지": (draw_n((a.reps, 60)), -a.shift),
    }
    for name, (n, mu) in scen.items():
        x = rng.normal(mu, np.sqrt(var(n)))
        rows.append({"항목": name,
                     "분산 하나": float(np.mean(rl(stat_path(x, n, 1), hs[1]) <= 10)),
                     "가변 표본": float(np.mean(rl(stat_path(x, n, 2), hs[2]) <= 10))})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 120)
    print(f"σ_w={a.sw}, σ_b={a.sb}, h(분산 하나)={hs[1]:.2f}, h(가변 표본)={hs[2]:.2f}")
    print(df.to_string(index=False, float_format=lambda v: f"{v*100:.2f}%"))
    if a.out:
        df.to_csv(a.out, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
