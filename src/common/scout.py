"""영입 전 점검(화면 5): 한 투수의 MLB·트리플A 시즌을 요약한다. 자료 수집·실행은 src/16_scout.py가 한다."""
from __future__ import annotations

import numpy as np
import pandas as pd

from src.common import labels as lb


def season_summary(table: pd.DataFrame) -> dict:
    """한 투수-시즌(등판 순)의 요약: 등판 수, 감시 등판 수, 시작 구간 평균 구속, 마지막 5등판 평균 구속, 그 차이, 경보 수, 첫 경보 날짜."""
    t = table.sort_values("game_date")
    base = t[t["phase"] == "baseline"]
    mon = t[t["phase"] == "monitor"]
    last5 = t.tail(5)
    first_alarm = mon.loc[mon["velo_alarm"] | mon["change_alarm"], "game_date"].min()
    fb = t["primary_fb"].mode().iloc[0] if "primary_fb" in t and t["primary_fb"].notna().any() else None
    return {"outings": int(len(t)), "monitored": int(len(mon)), "role": t["role"].iloc[0], "league": t["league"].iloc[0], "fb": fb,
            "velo_start": float(base["velo"].mean()) if len(base) else float("nan"),
            "velo_last5": float(last5["velo"].mean()), "velo_change": float(last5["velo"].mean() - base["velo"].mean()) if len(base) else float("nan"),
            "velo_max_index": float(mon["velo_index"].max()) if len(mon) else float("nan"),
            "alarms_velo": int(mon["velo_alarm"].sum()), "alarms_change": int(mon["change_alarm"].sum()),
            "first_alarm": None if pd.isna(first_alarm) else pd.Timestamp(first_alarm).strftime("%Y-%m-%d"),
            "first_date": pd.Timestamp(t["game_date"].iloc[0]).strftime("%Y-%m-%d"), "last_date": pd.Timestamp(t["game_date"].iloc[-1]).strftime("%Y-%m-%d")}


def arm_il(labels: pd.DataFrame, pitcher: int, season: int) -> dict | None:
    """그 투수-시즌의 첫 팔꿈치·어깨 IL (최종 라벨 기준). 없으면 None."""
    il = labels[(labels["pitcher"] == pitcher) & (labels["season"] == season) & labels["part"].isin(["elbow", "shoulder"])].sort_values("il_date")
    if il.empty:
        return None
    first = il.iloc[0]
    return {"date": pd.Timestamp(first["il_date"]).strftime("%Y-%m-%d"), "part": first["part"]}


def timeline(table: pd.DataFrame) -> list[dict]:
    """여러 시즌의 등판을 시간순으로 이어 붙인 구속 시계열 (리그·시즌·경보 표시 포함)."""
    t = table.sort_values(["game_date", "game_pk"])
    return [{"date": pd.Timestamp(r.game_date).strftime("%Y-%m-%d"), "season": int(r.season), "league": r.league, "velo": None if pd.isna(r.velo) else round(float(r.velo), 2),
             "alarm": bool(r.velo_alarm or r.change_alarm), "phase": r.phase, "velo_index": None if pd.isna(r.velo_index) else round(float(r.velo_index), 3)}
            for r in t.itertuples()]


def nan_to_none(d: dict) -> dict:
    return {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in d.items()}


def _part(reason: str, rules: dict) -> str:
    """IL 사유 문구의 부위: shoulder / elbow / other(다른 부위) / unknown(사유 없음). 좌우·투구 팔 대조는 하지 않는다 (참고용)."""
    if not reason:
        return "unknown"
    if lb._has(rules["shoulder_keywords"], reason):
        return "shoulder"
    if lb._has([w for w in rules["arm_keywords"] if w not in rules["shoulder_keywords"]], reason):
        return "elbow"
    return "other"


def il_placements(transactions: pd.DataFrame, ids: list[int], rules: dict) -> pd.DataFrame:
    """트리플A 거래 기록에서 목록 투수들의 새 IL 등재를 뽑는다: pitcher, season, il_date, days, part, reason.
    MLB 라벨(02_labels, 수기 검토)과 달리 자동 분류만 하고, 사유 문구가 없으면 부위를 unknown으로 둔다."""
    wanted = set(int(i) for i in ids)
    rows = []
    for t in transactions.itertuples(index=False):
        if t.person_id not in wanted:
            continue
        p = lb.parse_placement(t.description, rules["il_days"])
        if p is None:
            continue
        effective = t.effective_date if isinstance(t.effective_date, str) else None
        when, _ = lb.il_date(p["retro"], effective, t.date, rules["max_retro_days"])
        rows.append({"pitcher": int(t.person_id), "season": when.year, "il_date": pd.Timestamp(when), "days": p["days"],
                     "part": _part(p["reason"], rules), "reason": p["reason"] or None, "description": t.description})
    out = pd.DataFrame(rows, columns=["pitcher", "season", "il_date", "days", "part", "reason", "description"])
    return out.drop_duplicates(["pitcher", "il_date", "description"]).drop(columns="description").reset_index(drop=True)


def season_il(placements: pd.DataFrame, pitcher: int, season: int) -> dict | None:
    """그 투수-시즌의 IL 요약: 팔꿈치·어깨 등재가 있으면 그중 첫 번째, 없으면 첫 등재. count는 그 시즌 등재 횟수. 없으면 None."""
    mine = placements[(placements["pitcher"] == pitcher) & (placements["season"] == season)].sort_values("il_date")
    if mine.empty:
        return None
    arm = mine[mine["part"].isin(["elbow", "shoulder"])]
    first = (arm if len(arm) else mine).iloc[0]
    return {"date": first["il_date"].strftime("%Y-%m-%d"), "part": first["part"], "reason": first["reason"] if isinstance(first["reason"], str) else None, "count": int(len(mine))}


# ---------- 시즌 성적 (2026-10-21 사용자: 스카우트가 보는 지표 — 맥락 정보, 경보 신호와 섞지 않음) ----------
COUNTS = ["gamesPitched", "gamesStarted", "outs", "earnedRuns", "hits", "doubles", "triples", "homeRuns", "baseOnBalls", "hitByPitch",
          "strikeOuts", "battersFaced", "atBats", "sacFlies", "groundOuts", "airOuts", "numberOfPitches"]
SPORT = {1: "MLB", 11: "AAA"}


def season_counts(splits: list[dict]) -> dict[tuple[int, str], dict]:
    """MLB Stats API yearByYear 투구 기록(팀별 줄)을 (시즌, 리그)별 합계로. 정규시즌만, 팀 줄만 더한다."""
    out: dict[tuple[int, str], dict] = {}
    for s in splits:
        if s.get("gameType", "R") != "R" or s.get("sport", {}).get("id") not in SPORT or "team" not in s:
            continue
        key = (int(s["season"]), SPORT[s["sport"]["id"]])
        acc = out.setdefault(key, {c: 0 for c in COUNTS})
        for c in COUNTS:
            acc[c] += int(s["stat"].get(c) or 0)
    return out


def fip_constant(league: dict) -> float:
    """FIP 상수 = 리그 ERA − (13·HR + 3·(BB+HBP) − 2·K) / IP (리그 합계로)."""
    ip = league["outs"] / 3
    return 9 * league["earnedRuns"] / ip - (13 * league["homeRuns"] + 3 * (league["baseOnBalls"] + league["hitByPitch"]) - 2 * league["strikeOuts"]) / ip


def season_rates(c: dict, cfip: float | None, whiff: float | None) -> dict:
    """합계 → 화면 지표. 분모가 0이면 None."""
    r = lambda v: None if v is None or (isinstance(v, float) and np.isnan(v)) else round(float(v), 3)
    ip = c["outs"] / 3
    bf, ab = c["battersFaced"], c["atBats"]
    singles = c["hits"] - c["doubles"] - c["triples"] - c["homeRuns"]
    tb = singles + 2 * c["doubles"] + 3 * c["triples"] + 4 * c["homeRuns"]
    obp_den = ab + c["baseOnBalls"] + c["hitByPitch"] + c["sacFlies"]
    k, bb = (c["strikeOuts"] / bf, (c["baseOnBalls"] + c["hitByPitch"]) / bf) if bf else (None, None)
    fip = (13 * c["homeRuns"] + 3 * (c["baseOnBalls"] + c["hitByPitch"]) - 2 * c["strikeOuts"]) / ip + cfip if ip and cfip is not None else None
    return {"g": c["gamesPitched"], "gs": c["gamesStarted"], "ip": r(ip), "era": r(9 * c["earnedRuns"] / ip) if ip else None, "fip": r(fip),
            "whip": r((c["hits"] + c["baseOnBalls"]) / ip) if ip else None, "avg": r(c["hits"] / ab) if ab else None,
            "ops": r((c["hits"] + c["baseOnBalls"] + c["hitByPitch"]) / obp_den + tb / ab) if ab and obp_den else None,
            "k_pct": r(k), "bb_pct": r(bb), "k_bb": r(k - bb) if bf else None, "hr9": r(9 * c["homeRuns"] / ip) if ip else None,
            "go_ao": r(c["groundOuts"] / c["airOuts"]) if c["airOuts"] else None, "whiff": r(whiff),
            "p_ip": r(c["numberOfPitches"] / ip) if ip and c["numberOfPitches"] else None}


WHIFF = {"swinging_strike", "swinging_strike_blocked", "foul_tip", "missed_bunt"}
SWING = WHIFF | {"foul", "foul_bunt", "hit_into_play", "foul_pitchout", "swinging_pitchout"}


def whiff_rate(descriptions: pd.Series) -> float:
    """헛스윙률 = 헛스윙 ÷ 스윙 (Statcast description 기준)."""
    d = descriptions.astype(str)
    swings = int(d.isin(SWING).sum())
    return float(d.isin(WHIFF).sum() / swings) if swings else float("nan")
