"""등판 표 만들기 테스트 (SPEC 3.2·3.4·3.5). 실행: python -m pytest -q"""
import numpy as np
import pandas as pd
import pytest

from src.common import outings as og

FEATURES = {"primary_fastball_types": ["FF", "SI", "FC"], "core": ["velo", "rel_z", "arm_angle"],
            "min_fastballs": 3, "min_fastballs_sd": 3, "flip_rel_x_for_lhp": True}


def pitch(game, day, pitcher, hand, inning, half, ab, n, ptype, velo=94.0, rel_z=6.0, arm=40.0, rel_x=-2.0,
          event=None, desc="ball", plate_z=2.0, zone=5):
    return {"game_pk": game, "game_date": pd.Timestamp(day), "pitcher": pitcher, "p_throws": hand, "inning": inning,
            "inning_topbot": half, "at_bat_number": ab, "pitch_number": n, "pitch_type": ptype,
            "release_speed": velo, "release_pos_z": rel_z, "arm_angle": arm, "release_pos_x": rel_x,
            "release_extension": 6.5, "release_spin_rate": 2300.0, "plate_z": plate_z, "sz_top": 3.4, "sz_bot": 1.6,
            "zone": zone, "events": event, "description": desc}


@pytest.fixture
def season():
    rows = [
        # 경기 1: 투수 10(우투)이 선발. 포심 4개(하나는 팔 각도 결측), 슬라이더 1개, 자동 볼 1개
        pitch(1, "2023-04-01", 10, "R", 1, "Top", 1, 1, "FF", velo=95.0, rel_z=6.1, plate_z=3.0, zone=11),
        pitch(1, "2023-04-01", 10, "R", 1, "Top", 1, 2, "FF", velo=94.0, rel_z=6.0, event="strikeout"),
        pitch(1, "2023-04-01", 10, "R", 1, "Top", 2, 1, "SL", velo=85.0, event="single"),
        pitch(1, "2023-04-01", 10, "R", 1, "Top", 3, 1, "FF", velo=93.0, rel_z=5.9, event="grounded_into_double_play"),
        pitch(1, "2023-04-01", 10, "R", 2, "Top", 4, 1, "FF", velo=99.0, arm=np.nan, event="walk"),
        pitch(1, "2023-04-01", 10, "R", 2, "Top", 5, 1, None, velo=np.nan, rel_z=np.nan, arm=np.nan, desc="automatic_ball"),
        # 경기 1: 투수 20(좌투)이 7회에 구원. 싱커 2개, 포심 1개
        pitch(1, "2023-04-01", 20, "L", 7, "Top", 30, 1, "SI", velo=92.0, rel_x=2.0),
        pitch(1, "2023-04-01", 20, "L", 7, "Top", 30, 2, "SI", velo=93.0, rel_x=2.2, event="field_out"),
        pitch(1, "2023-04-01", 20, "L", 7, "Top", 31, 1, "FF", velo=94.0, rel_x=2.1, event="home_run"),
        # 경기 1: 상대 선발 30. 커터 1개
        pitch(1, "2023-04-01", 30, "R", 1, "Bot", 6, 1, "FC", velo=90.0, event="field_out"),
        # 경기 2: 투수 10이 다시 선발(포심 3개), 투수 20이 구원(싱커 3개)
        pitch(2, "2023-04-06", 10, "R", 1, "Top", 1, 1, "FF"),
        pitch(2, "2023-04-06", 10, "R", 1, "Top", 1, 2, "FF"),
        pitch(2, "2023-04-06", 10, "R", 1, "Top", 1, 3, "FF", event="truncated_pa"),
        pitch(2, "2023-04-06", 20, "L", 8, "Top", 40, 1, "SI", rel_x=2.0),
        pitch(2, "2023-04-06", 20, "L", 8, "Top", 40, 2, "SI", rel_x=2.0),
        pitch(2, "2023-04-06", 20, "L", 8, "Top", 40, 3, "SI", rel_x=2.0, event="strikeout_double_play"),
    ]
    return pd.DataFrame(rows)


@pytest.fixture
def built(season):
    outings, pitches_fb = og.build_outings(season, 2023, FEATURES)
    return outings.set_index(["pitcher", "game_pk"]), pitches_fb


def test_primary_fastball_is_the_most_thrown_of_the_allowed_types(built):
    outings, _ = built
    assert outings.loc[(10, 1), "primary_fb"] == "FF"
    assert outings.loc[(20, 1), "primary_fb"] == "SI"        # 시즌 전체로 싱커 5개 > 포심 1개
    assert outings.loc[(30, 1), "primary_fb"] == "FC"


def test_pitch_counts_ignore_automatic_calls_and_incomplete_fastballs(built):
    row = built[0].loc[(10, 1)]
    assert row["n_all"] == 5                      # 자동 볼은 던진 공이 아님
    assert row["n_fb"] == 3                       # 팔 각도가 없는 포심 1개는 품질 계산에서 뺌
    assert row["core_missing_frac"] == 0.25
    assert row["eligible"]
    assert not built[0].loc[(20, 1), "eligible"]  # 싱커 2개 < 하한 3


def test_features_are_means_over_valid_primary_fastballs(built):
    row = built[0].loc[(10, 1)]
    assert row["velo"] == pytest.approx(94.0)                  # 95, 94, 93 (99는 결측 투구라 제외)
    assert row["rel_z"] == pytest.approx(6.0)
    assert row["rel_z_sd"] == pytest.approx(0.1)
    assert row["high_rate"] == pytest.approx(1 / 3)            # plate_z 3.0 > 존 가운데 2.5 인 공 1개
    assert row["out_zone_rate"] == pytest.approx(1 / 3)
    assert np.isnan(built[0].loc[(20, 1), "rel_z_sd"])         # 주력 패스트볼이 SD 하한보다 적음


def test_release_side_is_mirrored_for_left_handers(built):
    outings, pitches_fb = built
    assert outings.loc[(20, 1), "rel_x"] == pytest.approx(-2.1)
    assert (pitches_fb.loc[pitches_fb["pitcher"] == 20, "rel_x"] < 0).all()
    assert outings.loc[(10, 1), "rel_x"] == pytest.approx(-2.0)


def test_starts_and_season_role(built):
    outings, _ = built
    assert outings.loc[(10, 1), "is_start"] and outings.loc[(30, 1), "is_start"]
    assert not outings.loc[(20, 1), "is_start"]
    assert outings.loc[(10, 2), "role"] == "SP" and outings.loc[(20, 2), "role"] == "RP"


def test_hits_walks_and_outs_come_from_events(built):
    outings, _ = built
    assert tuple(outings.loc[(10, 1), ["h", "bb", "outs"]]) == (1, 1, 3)     # 삼진 1 + 병살 2
    assert tuple(outings.loc[(20, 1), ["h", "bb", "outs"]]) == (1, 0, 1)
    assert outings.loc[(10, 2), "outs"] == 1                                 # 주자 아웃으로 끝난 타석
    assert outings.loc[(20, 2), "outs"] == 2


def test_fastball_pitch_table_has_only_complete_primary_fastballs(built):
    _, pitches_fb = built
    assert len(pitches_fb) == 3 + 3 + 2 + 3 + 1
    assert list(pitches_fb.columns) == ["pitcher", "season", "game_pk", "velo", "rel_z", "arm_angle", "rel_x",
                                        "extension", "spin"]
    assert not pitches_fb[["velo", "rel_z", "arm_angle"]].isna().any().any()
    assert set(pitches_fb["season"]) == {2023}


def test_events_on_automatic_calls_still_count(season):
    """고의4구나 피치 클록 위반 삼진은 투구 없이 선언되지만 볼넷·아웃으로는 세야 한다."""
    extra = pd.DataFrame([
        pitch(2, "2023-04-06", 20, "L", 8, "Top", 41, 1, None, velo=np.nan, rel_z=np.nan, arm=np.nan,
              event="intent_walk", desc="automatic_ball"),
        pitch(2, "2023-04-06", 20, "L", 8, "Top", 42, 1, None, velo=np.nan, rel_z=np.nan, arm=np.nan,
              event="strikeout", desc="automatic_strike"),
    ])
    outings, _ = og.build_outings(pd.concat([season, extra], ignore_index=True), 2023, FEATURES)
    row = outings.set_index(["pitcher", "game_pk"]).loc[(20, 2)]
    assert (row["bb"], row["outs"]) == (1, 3)      # 고의4구 1, 병살 삼진 2 + 자동 삼진 1
    assert row["n_all"] == 3                       # 던진 공은 싱커 3개뿐


def _one_pitcher(n_outings, rng, pitcher=1):
    rows = []
    for game in range(n_outings):
        day = rng.normal(0, 0.5)
        for v in day + rng.normal(0, 1.0, int(rng.integers(5, 30))):
            rows.append({"pitcher": pitcher, "season": 2022, "game_pk": game, "velo": 93 + v})
    return pd.DataFrame(rows)


def test_variance_components_recover_known_sd_and_agree_with_core():
    from src.core import stats_core as sc
    fb = _one_pitcher(300, np.random.default_rng(3))
    row = og.variance_components(fb, ["velo"], min_pitches=3, min_outings=8).iloc[0]
    assert row["outings"] == 300
    assert row["sigma_w_velo"] == pytest.approx(1.0, abs=0.05)
    assert row["sigma_b_velo"] == pytest.approx(0.5, abs=0.08)
    base = sc.phase1([g["velo"].to_numpy() for _, g in fb.groupby("game_pk")], floor=0.0)     # 같은 적률 방식
    assert row["sigma_w_velo"] == pytest.approx(float(np.sqrt(base.Sw[0, 0])))
    assert row["sigma_b_velo"] == pytest.approx(float(np.sqrt(base.Sb[0, 0])))


def test_variance_components_skip_short_outings_and_thin_pitcher_seasons():
    rng = np.random.default_rng(4)
    fb = pd.concat([_one_pitcher(20, rng, pitcher=1), _one_pitcher(5, rng, pitcher=2),
                    pd.DataFrame({"pitcher": 1, "season": 2022, "game_pk": 999, "velo": [80.0, 81.0]})])
    table = og.variance_components(fb, ["velo"], min_pitches=3, min_outings=8)
    assert list(table["pitcher"]) == [1]                 # 등판 5개뿐인 투수 2는 빠짐
    assert table.iloc[0]["outings"] == 20                # 2구짜리 등판은 세지 않음
