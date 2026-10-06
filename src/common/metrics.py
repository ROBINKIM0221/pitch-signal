"""평가 지표 (SPEC 3.13.3~3.13.4). 06_monitor(실측 보정 표)·08_evaluate·09_sealed가 같이 쓴다."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

OUTING = ["pitcher", "season", "game_pk"]
SET = ["case_id", "group", "pitcher", "season"]


def window_results(windows: pd.DataFrame, monitored: pd.DataFrame, alarm: str = "alarm",
                   index: str | None = None) -> pd.DataFrame:
    """사례·대조군마다 관찰 창 안에서 경보가 울렸는지(hit), 선행 등판 수(lead), 창 지수(top: 창 안 지수의 최댓값).

    windows: case_id, group, pitcher, season, game_pk (관찰 창 등판 한 줄에 하나)
    monitored: pitcher, season, game_pk, game_date와 경보 열(alarm), 지수 열(index, 없으면 top을 만들지 않음)
    lead는 창 안 첫 경보 등판부터 창의 마지막 등판까지의 등판 수(경보 등판 포함), 경보가 없으면 NaN.
    """
    columns = [*OUTING, "game_date", alarm] + ([index] if index else [])
    w = windows.merge(monitored[columns], on=OUTING, how="left", validate="many_to_one")
    if w[alarm].isna().any():
        raise ValueError(f"감시 결과에 없는 관찰 창 등판이 {int(w[alarm].isna().sum())}개 있습니다.")
    rows = []
    for keys, g in w.sort_values("game_date").groupby(SET, sort=False):
        rang = g[alarm].to_numpy(dtype=bool)
        row = dict(zip(SET, keys))
        row.update(hit=bool(rang.any()), lead=float(len(rang) - rang.argmax()) if rang.any() else np.nan)
        if index:
            row["top"] = float(g[index].max())
        rows.append(row)
    return pd.DataFrame(rows)


def detection(results: pd.DataFrame) -> dict:
    """탐지율(사례 중 창 안 경보 비율), 탐지 사례의 선행 등판 수 중앙값, 대조군 창 내 경보 비율."""
    cases, controls = results[results["group"] == "case"], results[results["group"] == "control"]
    return {"cases": len(cases), "detected": int(cases["hit"].sum()), "detection_rate": float(cases["hit"].mean()),
            "median_lead": float(cases["lead"].median()),
            "controls": len(controls), "control_window_rate": float(controls["hit"].mean())}


def concordance(results: pd.DataFrame) -> pd.Series:
    """사례마다 '사례의 창 지수가 자기 대조군의 창 지수보다 큰 비율'(같으면 0.5). 대조군이 없는 사례는 뺀다.

    평균이 짝지은 일치도다: 0.5면 차이 없음, 1이면 사례가 늘 큼 (H1의 판정 지표, SPEC 3.13.4).
    """
    case_top = results[results["group"] == "case"].set_index("case_id")["top"]
    controls = results[results["group"] == "control"]
    mine = controls["case_id"].map(case_top)
    win = (mine > controls["top"]).astype(float) + 0.5 * (mine == controls["top"])
    return win.groupby(controls["case_id"]).mean().rename("concordance")


def bootstrap_ci(values: pd.Series, reps: int, seed: int) -> tuple[float, float, float]:
    """사례 단위 값들의 (평균, 95% 구간 하한, 상한). 사례를 복원 추출하는 백분위 부트스트랩."""
    x = values.to_numpy(dtype=float)
    draws = np.random.default_rng(seed).integers(0, len(x), size=(reps, len(x)))
    means = x[draws].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(x.mean()), float(lo), float(hi)


def false_alarm_table(table: pd.DataFrame, alarm: str) -> pd.DataFrame:
    """대조군 감시 등판에서 역할별·시즌별(그리고 전체) 100등판당 경보 수와 실측 ARL0(경보 사이 평균 등판 수)."""
    rows = []
    for role in [*sorted(table["role"].unique()), "all"]:
        by_role = table if role == "all" else table[table["role"] == role]
        for season in [*sorted(by_role["season"].unique()), "all"]:
            part = by_role if season == "all" else by_role[by_role["season"] == season]
            n, a = len(part), int(part[alarm].sum())
            rows.append({"role": role, "season": season, "outings": n, "alarms": a,
                         "per100": 100 * a / n if n else np.nan, "arl0": n / a if a else np.nan})
    return pd.DataFrame(rows)


def mcnemar_exact(a: pd.Series, b: pd.Series) -> float:
    """두 방법의 사례별 탐지 여부를 짝지어 비교하는 McNemar 정확 검정(양쪽)의 p값. 불일치 쌍만 쓴다."""
    a, b = np.asarray(a, dtype=bool), np.asarray(b, dtype=bool)
    only_a, only_b = int((a & ~b).sum()), int((~a & b).sum())
    if only_a + only_b == 0:
        return 1.0
    return float(stats.binomtest(only_a, only_a + only_b, 0.5).pvalue)


def holm(pvalues: list[float]) -> list[float]:
    """Holm 단계적 보정. 입력 순서대로 보정한 p값을 돌려준다."""
    p = np.asarray(pvalues, dtype=float)
    order = np.argsort(p)
    adjusted = np.maximum.accumulate((len(p) - np.arange(len(p))) * p[order])      # 작은 p부터 (m − 순위 + 1)배, 앞 단계보다 작아지지 않게
    out = np.empty(len(p))
    out[order] = np.minimum(adjusted, 1.0)
    return out.tolist()


def window_flags(windows: pd.DataFrame, dates: pd.DataFrame, load: pd.DataFrame, flags: list[str]) -> pd.DataFrame:
    """사례·대조군마다 관찰 창 기간(첫 창 등판일~마지막 창 등판일) 안에 부하 표시가 있었는지 (표시별, 그리고 any). H4용.

    dates: pitcher, season, game_pk, game_date. load: pitcher, season, game_date와 flag_* 열 (적격 여부와 상관없이 모든 등판).
    """
    span = windows.merge(dates[[*OUTING, "game_date"]], on=OUTING).groupby(SET)["game_date"].agg(["min", "max"]).reset_index()
    rows = []
    for r in span.itertuples(index=False):
        inside = load[(load["pitcher"] == r.pitcher) & (load["season"] == r.season)
                      & load["game_date"].between(r.min, r.max)]
        hit = {f: bool(inside[f].any()) for f in flags}
        rows.append({"case_id": r.case_id, "group": r.group, "pitcher": r.pitcher, "season": r.season, **hit, "any": any(hit.values())})
    return pd.DataFrame(rows)


def alarm_followup(table: pd.DataFrame, labels: pd.DataFrame, days: int = 30, alarm: str = "velo_alarm") -> dict:
    """사후 지표(사전 등록 아님): 경보가 울린 등판 뒤 days일 안에 팔 부상 IL이 있는 비율과, 경보 없는 등판의 같은 비율. lift = 둘의 비.

    labels: pitcher, il_date(팔꿈치·어깨만 넘길 것). 같은 투수의 IL 중 등판 날짜보다 뒤이고 days일 이내인 것이 있으면 '뒤따름'으로 센다.
    """
    il = labels.groupby("pitcher")["il_date"].apply(lambda s: np.sort(pd.to_datetime(s).to_numpy()))
    dates = pd.to_datetime(table["game_date"]).to_numpy()
    followed = np.zeros(len(table), dtype=bool)
    for i, (pitcher, d) in enumerate(zip(table["pitcher"].to_numpy(), dates)):
        events = il.get(pitcher)
        if events is None:
            continue
        nxt = events[events > d]
        followed[i] = len(nxt) > 0 and (nxt[0] - d) <= np.timedelta64(days, "D")
    flag = table[alarm].to_numpy().astype(bool)
    a, o = followed[flag], followed[~flag]
    alarm_rate, other_rate = (a.mean() if len(a) else np.nan), (o.mean() if len(o) else np.nan)
    return {"days": days, "alarms": int(flag.sum()), "alarm_followed": int(a.sum()), "alarm_rate": float(alarm_rate),
            "other": int((~flag).sum()), "other_followed": int(o.sum()), "other_rate": float(other_rate),
            "lift": float(alarm_rate / other_rate) if other_rate else np.nan}
