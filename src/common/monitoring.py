"""기준선과 감시 (SPEC 3.7~3.8). 06_monitor·07_comparators·08_evaluate·09_sealed가 같이 쓴다.

주 방식은 '움직이는 기준선'이다. 투수의 평소(수준)가 등판마다 조금씩 움직인다고 보고, 등판마다 다음 등판의
예상값을 갱신하면서 예상과 실제의 차이를 표준화해 감시한다. 평소가 움직이는 크기(Q)와 등판마다 흔들리는
크기(Σ_e)는 개발셋 전체에서 역할별로 합동 추정하고, 등판 안 공분산 Σ_w는 투수 본인의 시작 구간에서 추정한다.
'고정 기준선'(시즌 초 평균에 계속 비교)은 왜 바꿨는지 보여 주는 비교용으로만 남겨 둔다.

통계 계산(표준화, T², MEWMA)은 src/core/stats_core.py를 그대로 쓰고, 여기서는 그 함수에 넘길 값을 만든다.
등판 배열은 (투구 수, 특징 수) 모양이고, '단위를 없앤' 값은 scale_factors로 나눈 값이다.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.common import baseline_window as bw
from src.core import stats_core as sc


def _lift(matrix: np.ndarray, floor: float) -> np.ndarray:
    """대칭 행렬의 고윳값을 floor 이상으로 올린다 (양정치 보장)."""
    w, v = np.linalg.eigh((matrix + matrix.T) / 2)
    return v @ np.diag(np.maximum(w, floor)) @ v.T


def outing_arrays(pitches_fb, features: list[str]) -> dict[tuple, np.ndarray]:
    """투구 표를 {(pitcher, season, game_pk): (투구 수, 특징 수) 배열}로 묶는다. 열 순서는 features 그대로."""
    return {key: group[features].to_numpy(dtype=float)
            for key, group in pitches_fb.groupby(["pitcher", "season", "game_pk"])}


# ---------------------------------------------------------------------------
# 1. 움직이는 기준선
# ---------------------------------------------------------------------------
@dataclass
class Dynamics:
    """평소가 움직이는 방식 (역할별 합동 추정값, 단위를 없앤 값)."""
    Q: np.ndarray       # 평소(수준)가 한 등판 사이에 움직이는 공분산
    Se: np.ndarray      # 등판마다 흔들리는 공분산 (투구 수에 따라 줄어드는 표본 잡음 Σ_w/n은 따로)


@dataclass
class Followed:
    u: np.ndarray           # 감시 등판별 표준화한 예측 오차 (등판 수 × 특징 수). 정상이면 N(0, I)
    expected: np.ndarray    # 감시 등판별 예상값 = 그 등판 직전까지의 평소 (등판 수 × 특징 수)
    cov: np.ndarray         # 감시 등판별 예측 오차의 공분산 (등판 수 × 특징 수 × 특징 수)


def start_up(outings: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """시작 구간(기준선) 등판들로 단위를 없애는 값과 투수 본인의 Σ_w(단위 없앤 값)를 구한다."""
    scale = sc.scale_factors(outings)
    return scale, sc.phase1([o / scale for o in outings], floor=-np.inf).Sw


def pooled_dynamics(seasons: list[tuple], q_floor: float, e_floor: float) -> Dynamics:
    """여러 투수-시즌에서 Q와 Σ_e를 적률로 합동 추정한다.

    seasons: (등판 평균 T×p, 투구 수 T, Σ_w) 목록. 모두 단위를 없앤 값이고 등판은 시간순이다.
    이웃한 등판의 차 d_t = x̄_t − x̄_{t−1}에서
      Cov(d_t) = Q + 2Σ_e + Σ_w(1/n_t + 1/n_{t−1}),   Cov(d_t, d_{t−1}) = −Σ_e − Σ_w/n_{t−1}
    """
    square = cross = noise_now = noise_shared = 0.0
    count = 0
    for means, n, sw in seasons:
        d = np.diff(means, axis=0)
        if len(d) < 2:
            continue
        now, before, inv = d[1:], d[:-1], 1 / n
        square = square + now.T @ now
        cross = cross + (now.T @ before + before.T @ now) / 2
        noise_now = noise_now + sw * (inv[2:] + inv[1:-1]).sum()
        noise_shared = noise_shared + sw * inv[1:-1].sum()
        count += len(now)
    se = -(cross + noise_shared) / count
    q = (square - noise_now) / count - 2 * se
    return Dynamics(Q=_lift(q, q_floor), Se=_lift(se, e_floor))


def follow(means: np.ndarray, n: np.ndarray, sw: np.ndarray, dynamics: Dynamics, n_start: int,
           skip_ucl: float) -> Followed:
    """한 투수-시즌의 등판 평균을 시간순으로 따라가며, 시작 구간 뒤 등판마다 예측 오차를 표준화한다.

    첫 등판에서 출발해 등판마다 평소(수준)를 갱신한다(칼만 필터). 투구 수가 적은 등판은 덜 반영된다.
    앞의 n_start개 등판은 시작 구간이라 감시하지 않고 평소를 잡는 데만 쓰며, 그 안에서 예상과 크게 다른
    등판(T² > skip_ucl)은 평소 갱신에 쓰지 않는다. 감시 구간에서는 모든 등판을 반영한다.
    """
    p = means.shape[1]
    level, spread = means[0].astype(float), dynamics.Se + sw / n[0]
    u, expected, cov = [], [], []
    for t in range(1, len(means)):
        ahead = spread + dynamics.Q
        base = sc.Baseline(mu=level, Sb=ahead + dynamics.Se, Sw=sw, n_outings=t)
        total = base.Sb + sw / n[t]
        u_t = sc.outing_u(means[t], n[t], base)
        if t >= n_start:
            u.append(u_t)
            expected.append(level)
            cov.append(total)
        elif sc.t2_stat(u_t) > skip_ucl:
            spread = ahead
            continue
        gain = ahead @ np.linalg.inv(total)
        level, spread = level + gain @ (means[t] - level), (np.eye(p) - gain) @ ahead
    return Followed(u=np.array(u).reshape(-1, p), expected=np.array(expected).reshape(-1, p),
                    cov=np.array(cov).reshape(-1, p, p))


def dynamic_table(outings: pd.DataFrame, fits: pd.DataFrame, dynamics: dict, rules: dict, features: list[str],
                  skip_ucl: float, velo: str = "velo") -> pd.DataFrame:
    """시작 구간 뒤 적격 등판(감시 대상)마다 움직이는 기준선으로 표준화한 값을 붙인 표를 시간순으로 돌려준다.

    fits: 투수-시즌별 scale·Sw·n_baseline (06_monitor --baselines가 저장한 표). dynamics: {역할: Dynamics}
    열: pitcher, season, role, game_pk, game_date, n_fb, u_<특징>, t2, expected_<특징>, sd_<특징>, cov, uv
    expected·sd는 원래 단위의 예상값과 예측 오차 표준편차, cov는 예측 오차의 공분산(원래 단위, 한 줄로 편 값,
    경보 원인 분해에 씀), uv는 구속 하나만으로 같은 계산을 한 값이다.
    """
    marked = outings.assign(phase=bw.phase(outings, rules).to_numpy())
    marked = marked[marked["phase"] != ""].sort_values(bw.ORDER)
    fitted = {(f["pitcher"], f["season"]): f for f in fits.to_dict("records")}
    v = features.index(velo)
    parts = []
    for (pitcher, season), group in marked.groupby(["pitcher", "season"], sort=False):
        fit = fitted[(pitcher, season)]
        scale, p = np.array(fit["scale"], dtype=float), len(features)
        sw = np.array(fit["Sw"], dtype=float).reshape(p, p)
        means, n = group[features].to_numpy(dtype=float) / scale, group["n_fb"].to_numpy(dtype=float)
        role_dynamics, n_start = dynamics[fit["role"]], int((group["phase"] == "baseline").sum())
        full = follow(means, n, sw, role_dynamics, n_start, skip_ucl)
        one = Dynamics(Q=role_dynamics.Q[v:v + 1, v:v + 1], Se=role_dynamics.Se[v:v + 1, v:v + 1])
        velo_only = follow(means[:, v:v + 1], n, sw[v:v + 1, v:v + 1], one, n_start, sc.t2_ucl(1, rules["refine_alpha"]))
        part = group.loc[group["phase"] == "monitor", ["pitcher", "season", "role", "game_pk", "game_date", "n_fb"]].copy()
        for j, f in enumerate(features):
            part[f"u_{f}"] = full.u[:, j]
            part[f"expected_{f}"] = full.expected[:, j] * scale[j]
            part[f"sd_{f}"] = np.sqrt(full.cov[:, j, j]) * scale[j]
        part["t2"] = (full.u ** 2).sum(axis=1)
        part["cov"] = [c.ravel().tolist() for c in full.cov * np.outer(scale, scale)]
        part["uv"] = velo_only.u[:, 0]
        parts.append(part)
    return pd.concat(parts, ignore_index=True)


def run_charts(table: pd.DataFrame, features: list[str], limits: dict, reset_after_alarm: bool) -> pd.DataFrame:
    """표준화한 표에 λ별 MEWMA 통계량(q_<λ>)과 경보(alarm_<λ>)를 붙인다.

    limits: {λ: (MEWMA 한계 h, T² 한계)}. 투수-시즌마다 새로 시작한다 (표는 시간순이어야 한다).
    """
    out = table.copy()
    columns = [f"u_{f}" for f in features]
    for lam, (h, ucl) in limits.items():
        q, alarm = np.zeros(len(out)), np.zeros(len(out), dtype=bool)
        for rows in out.groupby(["pitcher", "season"], sort=False).indices.values():
            result = sc.monitor(out.iloc[rows][columns].to_numpy(), h, ucl, lam, reset_after_alarm)
            q[rows], alarm[rows] = result.q, result.alarm
        out[f"q_{lam}"], out[f"alarm_{lam}"] = q, alarm
    return out


def _binned(table: pd.DataFrame, values: pd.Series, features: list[str], edges: list[int], name: str) -> pd.DataFrame:
    labels = [f"{a}~{b - 1}" for a, b in zip(edges, edges[1:])] + [f"{edges[-1]}+"]
    bins = pd.cut(values, [*edges, np.inf], right=False, labels=labels)
    grouped = table.groupby(bins, observed=True)
    out = pd.DataFrame({"outings": grouped.size(), **{f"var_u_{f}": grouped[f"u_{f}"].var() for f in features},
                        "mean_t2": grouped["t2"].mean()})
    return out.rename_axis(name).reset_index()


def calibration_by_n(table: pd.DataFrame, features: list[str], edges: list[int]) -> pd.DataFrame:
    """주력 패스트볼 수 구간별 등판 수, u의 분산(정상이면 1), T² 평균(정상이면 특징 수)."""
    return _binned(table, table["n_fb"], features, edges, "n_fb_bin")


def calibration_by_order(table: pd.DataFrame, features: list[str], edges: list[int]) -> pd.DataFrame:
    """시작 구간 뒤 몇 번째 감시 등판인지(1부터) 구간별 같은 표. 표는 투수-시즌 안에서 시간순이어야 한다."""
    order = table.groupby(["pitcher", "season"], sort=False).cumcount() + 1
    return _binned(table, order, features, edges, "order_bin")


def over_limit(by_n: pd.DataFrame, features: list[str], limit: float, min_outings: int) -> list[tuple]:
    """등판이 min_outings개 이상인 구간 가운데 u 분산이 limit를 넘는 (구간, 특징, 분산) 목록 (평가 계획서 4.1 규칙)."""
    full = by_n[by_n["outings"] >= min_outings]
    return [(row["n_fb_bin"], f, float(row[f"var_u_{f}"])) for _, row in full.iterrows() for f in features
            if row[f"var_u_{f}"] > limit]


# ---------------------------------------------------------------------------
# 2. 고정 기준선 (비교용)
# ---------------------------------------------------------------------------
def raw_sigma_b(outings: list[np.ndarray]) -> np.ndarray:
    """기준선 하나의 Σ_b 적률 추정값 (고윳값 하한을 적용하지 않은 값). 단위를 없앤 등판을 넘긴다."""
    return sc.phase1(outings, floor=-np.inf).Sb


def pooled_sigma_b(baselines: list[list[np.ndarray]], floor: float) -> np.ndarray:
    """여러 기준선의 Σ_b 추정값을 (등판 수 − 1) 가중 평균하고 고윳값을 floor 이상으로 올린다."""
    weights = np.array([len(b) - 1 for b in baselines], dtype=float)
    pooled = np.tensordot(weights, np.array([raw_sigma_b(b) for b in baselines]), axes=1) / weights.sum()
    return _lift(pooled, floor)


def assemble(outings: list[np.ndarray], sigma_b: np.ndarray) -> sc.Baseline:
    """투수 본인의 μ·Σ_w와 합동 Σ_b로 고정 기준선을 만든다.

    기준선 등판 수 m이 작아 μ가 부정확한 만큼 한계를 넓힌다:
    감시에 쓰는 등판 간 공분산 = Σ_b·(1 + 1/m) + Σ_w·mean(1/n_i)/m
    """
    own = sc.phase1(outings, floor=-np.inf)          # mu와 Sw만 쓴다
    m = len(outings)
    widened = sigma_b * (1 + 1 / m) + own.Sw * np.mean([1 / len(o) for o in outings]) / m
    return sc.Baseline(mu=own.mu, Sb=widened, Sw=own.Sw, n_outings=m)


def refine(outings: list[np.ndarray], sigma_b: np.ndarray, ucl: float) -> list[int]:
    """기준선에서 뺄 등판의 위치. 각 등판을 뺀 나머지로 만든 기준선에 대한 T²가 ucl을 넘는 등판이다 (1회).

    빼고 남는 등판이 3개 미만이 되면 아무것도 빼지 않는다.
    """
    over = []
    for i, o in enumerate(outings):
        rest = assemble(outings[:i] + outings[i + 1:], sigma_b)
        if sc.t2_stat(sc.outing_u(o.mean(0), len(o), rest)) > ucl:
            over.append(i)
    return over if len(outings) - len(over) >= 3 else []


def fit_baseline(outings: list[np.ndarray], sigma_b: np.ndarray, ucl: float):
    """원래 단위의 기준선 등판들 → (단위를 없애는 값, 고정 기준선, 정제로 뺀 등판 위치)."""
    scale = sc.scale_factors(outings)
    unitless = [o / scale for o in outings]
    removed = refine(unitless, sigma_b, ucl)
    return scale, assemble([o for i, o in enumerate(unitless) if i not in removed], sigma_b), removed


def standardize(outings: list[np.ndarray], scale: np.ndarray, baseline: sc.Baseline) -> np.ndarray:
    """원래 단위의 등판들을 고정 기준선에 대해 투구 수에 맞춰 표준화한 u (등판 수 × 특징 수)로 바꾼다."""
    return np.array([sc.outing_u((o / scale).mean(0), len(o), baseline) for o in outings])


def marginal(baseline: sc.Baseline, index: list[int]) -> sc.Baseline:
    """고정 기준선에서 일부 특징만 남긴다 (예: 구속 하나로 보는 차트)."""
    grid = np.ix_(index, index)
    return sc.Baseline(mu=baseline.mu[index], Sb=baseline.Sb[grid], Sw=baseline.Sw[grid], n_outings=baseline.n_outings)


def to_baseline(fit) -> sc.Baseline:
    """fits 표의 한 줄에 저장한 고정 기준선(fixed_mu·fixed_Sb·fixed_Sw)을 되돌린다."""
    p = len(fit["fixed_mu"])
    return sc.Baseline(mu=np.array(fit["fixed_mu"], dtype=float),
                       Sb=np.array(fit["fixed_Sb"], dtype=float).reshape(p, p),
                       Sw=np.array(fit["fixed_Sw"], dtype=float).reshape(p, p),
                       n_outings=int(fit["n_baseline"] - fit["fixed_removed"]))


def fixed_table(outings: pd.DataFrame, arrays: dict, fits: pd.DataFrame, rules: dict,
                features: list[str]) -> pd.DataFrame:
    """고정 기준선으로 표준화한 감시 등판 표 (비교용). 열: pitcher, season, role, game_pk, game_date, n_fb, u_<특징>, t2"""
    monitored = outings[bw.phase(outings, rules) == "monitor"].sort_values(bw.ORDER)
    fitted = {(f["pitcher"], f["season"]): f for f in fits.to_dict("records")}
    parts = []
    for (pitcher, season), group in monitored.groupby(["pitcher", "season"], sort=False):
        fit = fitted[(pitcher, season)]
        u = standardize([arrays[(pitcher, season, game)] for game in group["game_pk"]],
                        np.array(fit["scale"], dtype=float), to_baseline(fit))
        part = group[["pitcher", "season", "role", "game_pk", "game_date", "n_fb"]].copy()
        for j, f in enumerate(features):
            part[f"u_{f}"] = u[:, j]
        part["t2"] = (u ** 2).sum(axis=1)
        parts.append(part)
    return pd.concat(parts, ignore_index=True)
