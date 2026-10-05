"""기준선 등판 수가 적을 때 Σ_b 추정 방식 비교 시뮬레이션 (SPEC 3.7절, 변경 기록 2026. 10. 5.).

① 투수별 추정(기준선 8·15등판으로 Σ_b를 투수마다 추정, leave-one-out 정제 포함)과
② 합동 추정(여러 투수의 기준선을 모아 Σ_b를 한 번 추정, 평균 추정 오차 보정, 정제 생략)을
이론 관리한계(T² α = 0.001, MEWMA h는 ARL0 = 100 이론값)로 감시했을 때의 정상 상태 오경보율을 비교한다.
데이터는 평소 그대로인 가상 투수(정규분포)이고 특징은 3개다. 목표 오경보율은 100등판당 1회.

사용 예:
    python tools/sim_small_baseline.py --out reports/tables/sim_small_baseline.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.core import stats_core as sc  # noqa: E402

P = 3
SB_BASE = np.array([0.25, 0.30, 0.20])     # 등판 간 분산 (등판 안 투구별 분산 = 1 기준)
ROLES = {                                   # 역할: (기준선 등판 수, 기준선 최소 누적 투구, 감시 등판 수, 평균 투구 수, 하한, 상한)
    "선발": (8, 0, 22, 45, 15, 80),
    "불펜": (15, 120, 45, 8, 3, 25),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pitchers", type=int, default=2000, help="역할별 가상 투수 수")
    ap.add_argument("--hetero", type=float, default=0.5, help="투수 간 Σ_b 차이 (로그 척도 표준편차)")
    ap.add_argument("--lam", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    ucl = sc.t2_ucl(P, 0.001)
    h = sc.calibrate_h(P, a.lam, ucl, target=100, n_sim=4000, max_len=1500, seed=0)

    def draw(m, sb, mean_n, lo, hi):
        outs = []
        for _ in range(m):
            n = int(np.clip(rng.poisson(mean_n), lo, hi))
            outs.append(rng.multivariate_normal(np.zeros(P), sb) + rng.standard_normal((n, P)))
        return outs

    def baseline(sb, m, min_cum, mean_n, lo, hi):
        outs = draw(m, sb, mean_n, lo, hi)
        while sum(len(o) for o in outs) < min_cum:
            outs += draw(1, sb, mean_n, lo, hi)
        sd = sc.scale_factors(outs)
        return [o / sd for o in outs], sd

    def raw_sb(outs):
        xbar = np.array([o.mean(0) for o in outs])
        return np.cov(xbar, rowvar=False) - np.mean([1 / len(o) for o in outs]) * sc.phase1(outs).Sw

    rows = []
    for role, (m, min_cum, m_mon, mean_n, lo, hi) in ROLES.items():
        true_sb = lambda: np.diag(SB_BASE * np.exp(rng.normal(0, a.hetero, P)))
        pool = np.mean([raw_sb(baseline(true_sb(), m, min_cum, mean_n, lo, hi)[0]) for _ in range(a.pitchers)], axis=0)
        U = {"투수별 추정": [], "합동 추정": []}
        dropped = total = 0
        for _ in range(a.pitchers):
            sb = true_sb()
            base, sd = baseline(sb, m, min_cum, mean_n, lo, hi)
            mon = [o / sd for o in draw(m_mon, sb, mean_n, lo, hi)]
            own, removed = sc.phase1_refined(base, ucl=sc.t2_ucl(P, 0.01))
            dropped, total = dropped + len(removed), total + len(base)
            plain = sc.phase1(base)
            k = len(base)
            widened = pool * (1 + 1 / k) + plain.Sw * np.mean([1 / len(o) for o in base]) / k
            pooled = sc.Baseline(plain.mu, widened, plain.Sw, k)
            for name, b in (("투수별 추정", own), ("합동 추정", pooled)):
                U[name].append(np.array([sc.outing_u(o.mean(0), len(o), b) for o in mon]))
        for name, paths in U.items():
            t2 = np.concatenate([(u ** 2).sum(1) for u in paths])
            both = sc.empirical_false_alarm_rate([sc.monitor(u, h=h, ucl=ucl, lam=a.lam) for u in paths])
            rows.append({"역할": role, "기준선 등판": m, "방식": name,
                         "u 분산 (특징 평균)": np.concatenate(paths).var(0).mean(),
                         "T² 단독 오경보 (/100등판)": 100 * (t2 > ucl).mean(),
                         "전체 오경보 (/100등판)": both,
                         "정제로 빠진 기준선 등판 (%)": 100 * dropped / total if name == "투수별 추정" else 0.0})
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 160)
    print(f"이론 관리한계: T² {ucl:.2f}, h {h:.2f} (λ = {a.lam}), 목표 오경보 1.0/100등판")
    print(df.to_string(index=False, float_format=lambda v: f"{v:.2f}"))
    if a.out:
        df.to_csv(a.out, index=False, encoding="utf-8-sig")


if __name__ == "__main__":
    main()
