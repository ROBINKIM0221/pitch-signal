"""등판 표 만들기 (SPEC 3.2·3.4·3.5). 한 시즌 투구 표를 '투수 × 경기' 한 줄짜리 표로 줄인다."""
from __future__ import annotations

import numpy as np
import pandas as pd

# 특징 이름 → Statcast 열 (SPEC 3.5의 F1~F6)
FEATURE_COLUMNS = {"velo": "release_speed", "rel_z": "release_pos_z", "arm_angle": "arm_angle",
                   "rel_x": "release_pos_x", "extension": "release_extension", "spin": "release_spin_rate"}
OUT_OF_ZONE = [11, 12, 13, 14]                              # Statcast zone 번호 중 스트라이크 존 밖 (F9)
AUTOMATIC = ["automatic_ball", "automatic_strike"]          # 투구 없이 선언된 볼·스트라이크
HITS = ["single", "double", "triple", "home_run"]
WALKS = ["walk", "intent_walk"]
OUTS = {"strikeout": 1, "field_out": 1, "force_out": 1, "sac_fly": 1, "sac_bunt": 1, "fielders_choice_out": 1,
        "other_out": 1, "truncated_pa": 1,                  # truncated_pa: 주자 아웃으로 이닝이 끝난 타석
        "caught_stealing_2b": 1, "caught_stealing_3b": 1, "caught_stealing_home": 1,
        "pickoff_1b": 1, "pickoff_2b": 1, "pickoff_3b": 1,
        "pickoff_caught_stealing_2b": 1, "pickoff_caught_stealing_3b": 1, "pickoff_caught_stealing_home": 1,
        "grounded_into_double_play": 2, "double_play": 2, "strikeout_double_play": 2,
        "sac_fly_double_play": 2, "sac_bunt_double_play": 2, "triple_play": 3}
KEY = ["pitcher", "game_pk"]


def primary_fastball(pitches: pd.DataFrame, fb_types: list[str]) -> pd.Series:
    """투수별 주력 패스트볼: fb_types 중 그 시즌 가장 많이 던진 구종 (같으면 fb_types의 앞쪽)."""
    counts = (pitches[pitches["pitch_type"].isin(fb_types)]
              .groupby(["pitcher", "pitch_type"]).size().unstack(fill_value=0).reindex(columns=fb_types, fill_value=0))
    return counts.idxmax(axis=1)


def build_outings(pitches: pd.DataFrame, season: int, features: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """한 시즌 투구 표 → (등판 표, 주력 패스트볼 투구 표).

    주력 패스트볼 특징은 핵심 특징에 결측이 없는 주력 패스트볼 투구만으로 계산하고,
    투구 수(n_all)와 피안타·볼넷·아웃은 전 구종으로 센다.
    """
    p = pitches.copy()
    p["thrown"] = ~p["description"].isin(AUTOMATIC)      # 고의4구 등은 투구 수에서 빼되 볼넷·아웃으로는 센다
    p["primary_fb"] = p["pitcher"].map(primary_fastball(p, features["primary_fastball_types"]))
    p["is_primary"] = p["pitch_type"] == p["primary_fb"]
    core = [FEATURE_COLUMNS[f] for f in features["core"]]
    fb = p[p["is_primary"] & p[core].notna().all(axis=1)].copy()
    if features["flip_rel_x_for_lhp"]:
        fb.loc[fb["p_throws"] == "L", "release_pos_x"] *= -1

    out = p.groupby(KEY).agg(game_date=("game_date", "first"), primary_fb=("primary_fb", "first"),
                             n_all=("thrown", "sum"), n_primary=("is_primary", "sum"),
                             h=("events", lambda e: e.isin(HITS).sum()), bb=("events", lambda e: e.isin(WALKS).sum()),
                             outs=("events", lambda e: e.map(OUTS).sum()))
    by_outing = fb.groupby(KEY)
    out["n_fb"] = by_outing.size().reindex(out.index, fill_value=0)
    for name, column in FEATURE_COLUMNS.items():
        out[name] = by_outing[column].mean()
    out["rel_z_sd"] = by_outing["release_pos_z"].std().where(out["n_fb"] >= features["min_fastballs_sd"])
    located = fb.dropna(subset=["plate_z", "sz_top", "sz_bot"])
    out["high_rate"] = (located["plate_z"] > (located["sz_top"] + located["sz_bot"]) / 2).groupby(
        [located["pitcher"], located["game_pk"]]).mean()
    zoned = fb.dropna(subset=["zone"])
    out["out_zone_rate"] = zoned["zone"].isin(OUT_OF_ZONE).groupby([zoned["pitcher"], zoned["game_pk"]]).mean()

    first = (p[p["inning"] == 1].sort_values(["at_bat_number", "pitch_number"])
             .groupby(["game_pk", "inning_topbot"]).head(1))
    out["is_start"] = out.index.isin(list(zip(first["pitcher"], first["game_pk"])))
    out["role"] = np.where(out.groupby("pitcher")["is_start"].transform("mean") > 0.5, "SP", "RP")
    out["eligible"] = out["n_fb"] >= features["min_fastballs"]
    out["core_missing_frac"] = (1 - out["n_fb"] / out["n_primary"]).where(out["n_primary"] > 0)
    out["season"] = season
    out = out.reset_index().sort_values(["pitcher", "game_date", "game_pk"], ignore_index=True)
    columns = ["pitcher", "season", "game_pk", "game_date", "role", "is_start", "primary_fb", "n_fb", "n_all",
               "eligible", *FEATURE_COLUMNS, "rel_z_sd", "high_rate", "out_zone_rate", "h", "bb", "outs",
               "core_missing_frac"]

    pitches_fb = fb[KEY + list(FEATURE_COLUMNS.values())].rename(columns={v: k for k, v in FEATURE_COLUMNS.items()})
    pitches_fb.insert(1, "season", season)
    return out[columns], pitches_fb.reset_index(drop=True)


def variance_components(pitches_fb: pd.DataFrame, features: list[str], min_pitches: int,
                        min_outings: int) -> pd.DataFrame:
    """투수-시즌별 등판 안 표준편차(σ_w)와 등판 간 표준편차(σ_b). stats_core.phase1과 같은 적률 방식.

    σ_w² = 등판별 표본분산의 (n_i − 1) 가중 평균, σ_b² = Var(등판 평균) − mean(1/n_i)·σ_w² (음수면 0).
    투구가 min_pitches개 미만인 등판과, 그런 등판을 뺀 뒤 등판이 min_outings개 미만인 투수-시즌은 뺀다.
    """
    table = None
    for f in features:
        o = pitches_fb.groupby(["pitcher", "season", "game_pk"])[f].agg(["count", "mean", "var"])
        o = o[o["count"] >= min_pitches]
        o = o.assign(ss=(o["count"] - 1) * o["var"], df=o["count"] - 1, inv=1 / o["count"])
        ps = o.groupby(["pitcher", "season"]).agg(outings=("mean", "size"), ss=("ss", "sum"), df=("df", "sum"),
                                                  between=("mean", "var"), inv=("inv", "mean"))
        within = ps["ss"] / ps["df"]
        ps[f"sigma_w_{f}"] = np.sqrt(within)
        ps[f"sigma_b_{f}"] = np.sqrt((ps["between"] - ps["inv"] * within).clip(lower=0))
        ps = ps.loc[ps["outings"] >= min_outings, ["outings", f"sigma_w_{f}", f"sigma_b_{f}"]]
        table = ps if table is None else table.join(ps.drop(columns="outings"), how="inner")
    return table.reset_index()
