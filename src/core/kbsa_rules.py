"""고교 투구수 규정 엔진 (참조 구현).

KBSA 규정(설정 파일 highschool.kbsa)과 누적 부하(ACWR)를 계산한다.
- 규정 위반과 누적 부하 경보는 서로 다른 개념이므로 결과에서 분리해 표시한다.
- 이 파일은 임의로 수정하지 않는다 (저장소 규칙 4).
"""
from __future__ import annotations

import pandas as pd

DEFAULT_REST_TABLE = [(45, 0), (60, 1), (75, 2), (90, 3), (105, 4)]


def required_rest(pitches: int, rest_table=DEFAULT_REST_TABLE) -> int:
    """투구 수에 따른 의무 휴식일 수. 표의 상한을 넘으면 마지막 값을 쓴다."""
    for upper, rest in rest_table:
        if pitches <= upper:
            return rest
    return rest_table[-1][1]


def check_violations(log: pd.DataFrame, daily_max: int = 105,
                     rest_table=DEFAULT_REST_TABLE,
                     no_three_consecutive_days: bool = True) -> pd.DataFrame:
    """한 투수의 등판 기록에서 KBSA 규정 위반을 찾는다.

    log: columns = [date, pitches]  (같은 날 여러 경기면 합산한다)
    반환: columns = [date, rule, detail]
      rule ∈ {"daily_max", "rest", "three_days", "unknown"}
    의무 휴식일 r: d일에 던졌다면 다음 등판 가능일은 d + r + 1일.
    투구 수가 비어 있는 날(NaN)은 0으로 보지 않는다. 그날의 한도·휴식 판정은 'unknown'으로
    남기고, 등판한 사실은 3일 연속 등판 판정에 그대로 쓴다.
    """
    d = (log.assign(date=pd.to_datetime(log["date"]))
            .groupby("date", as_index=False)["pitches"].sum(min_count=1)
            .sort_values("date").reset_index(drop=True))
    out = []
    for i, row in d.iterrows():
        if pd.isna(row.pitches):
            out.append((row.date, "unknown", "투구 수 기록 없음 — 한도·휴식 판정 불가"))
        elif row.pitches > daily_max:
            out.append((row.date, "daily_max", f"{int(row.pitches)}구 > {daily_max}구"))
        if i + 1 < len(d) and not pd.isna(row.pitches):
            r = required_rest(int(row.pitches), rest_table)
            allowed = row.date + pd.Timedelta(days=r + 1)
            nxt = d.loc[i + 1, "date"]
            if nxt < allowed:
                out.append((nxt, "rest",
                            f"{row.date:%m/%d} {int(row.pitches)}구 → 휴식 {r}일 필요, "
                            f"{nxt:%m/%d} 등판"))
        if no_three_consecutive_days and i >= 2:
            if (d.loc[i, "date"] - d.loc[i - 2, "date"]).days == 2:
                out.append((row.date, "three_days", "3일 연속 등판"))
    return pd.DataFrame(out, columns=["date", "rule", "detail"])


def daily_series(log: pd.DataFrame, start=None, end=None) -> pd.Series:
    """등판 기록을 하루 단위 투구 수 시계열로 바꾼다.

    등판 없는 날은 0, 등판했지만 투구 수가 비어 있는 날은 NaN으로 둔다.
    NaN이 들어간 창의 누적·ACWR은 NaN(계산 불가)이 된다.
    """
    s = (log.assign(date=pd.to_datetime(log["date"]))
            .groupby("date")["pitches"].sum(min_count=1))
    idx = pd.date_range(start or s.index.min(), end or s.index.max(), freq="D")
    return s.reindex(idx, fill_value=0)


def acwr(daily: pd.Series, acute_days: int = 7, chronic_days: int = 21,
         coverage: pd.Series | None = None, min_coverage: float = 1.0) -> pd.DataFrame:
    """ACWR = 최근 acute_days일 합 ÷ (그 이전 chronic_days일 합 / (chronic_days/7)).

    coverage: 날짜별로 '그 팀 경기 기록이 수집된 기간인지'(bool) — 주어지면
      직전 chronic_days일 중 수집 기간 비율이 min_coverage 미만인 날은
      eligible=False로 표시한다 (기록이 비어 만성 부하가 과소 추정되는 것을 막기 위함).
    chronic이 0이면 ACWR은 계산하지 않는다(NaN).
    """
    acute = daily.rolling(acute_days, min_periods=acute_days).sum()
    prior = daily.shift(acute_days).rolling(chronic_days, min_periods=chronic_days).sum()
    chronic = prior / (chronic_days / 7)
    ratio = acute / chronic.where(chronic > 0)
    out = pd.DataFrame({"pitches": daily, "acute": acute, "chronic": chronic, "acwr": ratio})
    if coverage is not None:
        cov = (coverage.astype(float).reindex(daily.index, fill_value=0)
                       .shift(acute_days).rolling(chronic_days, min_periods=chronic_days).mean())
        out["eligible"] = (cov >= min_coverage) & ratio.notna()
    else:
        out["eligible"] = ratio.notna()
    return out


def window_limit_violations(daily: pd.Series, window_days: int, max_pitches: int) -> pd.DataFrame:
    """'window_days일 안에 max_pitches구 초과' 형태의 해외 규정 위반일을 찾는다.

    예: 일본 고교 '1주 500구' → window_days=7, max_pitches=500
    """
    roll = daily.rolling(window_days, min_periods=1).sum()
    hit = roll[(roll > max_pitches) & (daily > 0)]
    return pd.DataFrame({"date": hit.index, "window_sum": hit.values})
