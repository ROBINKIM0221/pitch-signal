"""KBSA 경기 기록 변환 (화면 3의 실제 입력). 설정은 config_kbsa.yaml의 datasets (시즌 모드·대회 모드).

data/raw/kbsa/record_detail_<game_idx>.html (KBSA 기록실 경기 기록, 1회 수집) →
  <name_map>                                    선수 실명 ↔ 등번호 표기 대응표 (저장소 밖, config의 name_map 경로)
  data/processed/hs_<key>_rows.parquet          등판표 (고교 모듈 입력 열 + 대회·상대·등판 구분·휴식일 주석; 선수는 코드)
  data/processed/hs_<key>_daily.parquet         투수별 하루 단위 값 (highschool.daily_table: 7일 합, ACWR)
  data/processed/hs_<key>_violations.csv        규정 위반·판정 불가 목록
  data/processed/hs_<key>_names.csv             학교 코드 ↔ 학교 실명, 투수 코드 ↔ 등번호 표기 (선수 실명 없음)
  reports/tables/hs_<key>_summary.csv           학교별 요약

사용 예:
    python -m src.17_kbsa_records                 # 모든 데이터셋
    python -m src.17_kbsa_records --only gyeonggi_2025
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

from src.common import highschool as hs
from src.common import hs_records as hr
from src.common import kbsa_boxscore as kb
from src.common.config import ROOT

RAW = ROOT / "data" / "raw" / "kbsa"
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
log = logging.getLogger("pitchsignal.hs_records")


def parse_games(game_ids: list[int]) -> pd.DataFrame:
    pages = {g: RAW / f"record_detail_{g}.html" for g in game_ids}
    missing = [g for g, p in pages.items() if not p.exists()]
    if missing:
        log.warning("기록 페이지가 없는 경기 %d개는 뺀다: %s", len(missing), missing[:10])
    games = [kb.parse_record_detail(p.read_text(encoding="utf-8"), g) for g, p in pages.items() if p.exists()]
    return kb.games_to_rows(games)


def season_games(cfg: dict, d: dict) -> tuple[list[int], pd.Series, set[str]]:
    """시즌 모드: 경기 목록(games_csv)에서 지역 리그 참가팀을 고르고, 그 팀이 나온 모든 경기를 대회 이름과 함께 돌려준다."""
    games = pd.read_csv(ROOT / cfg["games_csv"], encoding="utf-8-sig")
    teams = set(games.loc[games["lig_idx"].isin(d["region_leagues"]), ["team1", "team2"]].stack())
    pick = games[games["team1"].isin(teams) | games["team2"].isin(teams)].copy()

    def competition(league: str) -> str:
        for needle, name in d["competitions"].items():
            if needle in league:
                return name
        raise ValueError(f"대회 이름을 모르는 리그: {league}")

    comp = pd.Series([competition(x) for x in pick["league"]], index=pick["game_idx"].to_numpy())
    return pick["game_idx"].tolist(), comp, teams


def convert(key: str, cfg: dict, d: dict, rules: dict) -> dict:
    if d["mode"] == "tournament":
        ids, teams = list(d["games"]), None
        comp = pd.Series(d["overrides"]["competitions"][0], index=ids)
    else:
        ids, comp, teams = season_games(cfg, d)
    raw = hr.combine_stints(hr.mark_missing_detail(parse_games(ids)))
    if teams is not None:
        unknown = set(raw["team"]) - teams - set(raw["opponent"])
        if unknown:
            log.warning("리그 목록에 없는 팀 이름: %s", sorted(unknown))
        raw = raw[raw["team"].isin(teams)].reset_index(drop=True)          # 지역 밖 상대 팀 투수는 기록이 일부뿐이라 뺀다
    names = hr.name_map(raw)
    rules = {**rules, "schools": int(raw["team"].nunique())}
    rows = hr.input_rows(raw, names, comp, d.get("rounds"))
    problems = hs.problems(rows, rules)
    if len(problems):
        print(problems.to_string(index=False))
        raise SystemExit(f"{key}: 변환한 표가 입력 검사를 통과하지 못했습니다.")
    daily = hs.daily_table(rows, rules)
    violated = hs.violations(rows, daily, rules)
    outings = hr.annotate_outings(rows, rules["kbsa"])
    summary = hs.summary(daily, violated)
    school_name = names.drop_duplicates("school").set_index("school")["team"]

    outings.to_parquet(PROCESSED / f"hs_{key}_rows.parquet", compression="zstd", index=False)
    daily.to_parquet(PROCESSED / f"hs_{key}_daily.parquet", compression="zstd", index=False)
    violated.to_csv(PROCESSED / f"hs_{key}_violations.csv", index=False, encoding="utf-8-sig")
    names.drop(columns="name").to_csv(PROCESSED / f"hs_{key}_names.csv", index=False, encoding="utf-8-sig")
    summary.assign(학교명=summary["학교"].map(school_name)).to_csv(TABLES / f"hs_{key}_summary.csv", index=False, encoding="utf-8-sig")

    no_detail = sorted(int(g) for g in rows.loc[~rows["detail"], "game_no"].unique())
    second = outings[outings["gap_days"].notna()]
    log.info("%s(%s): 경기 %d(상세 기록 없는 경기 %d), 팀 %d, 투수 %d, 등판 %d(두 번 등판 합친 줄 %d), 투구 수 모르는 등판 %d",
             d["name"], d["mode"], rows["game_no"].nunique(), len(no_detail), rows["school"].nunique(), rows["pitcher"].nunique(), len(rows),
             int((rows["stints"] > 1).sum()), int(rows["pitches"].isna().sum()))
    log.info("규정 위반·판정 불가: %s | 두 번째 이후 등판 %d: 연투 %d, 최소 휴식만 채우고 등판 %d, 휴식 부족 %d",
             violated["rule"].value_counts().to_dict() or "없음", len(second), int((second["gap_days"] == 0).sum()),
             int((second["min_rest_exact"] == True).sum()), int((second["rest_ok"] == False).sum()))
    if d["mode"] == "season":
        per = daily.groupby("pitcher").agg(ok=("acwr_ok", "any"), flag=("acwr_flag", "any"))
        log.info("ACWR 계산 가능 투수 %d, 기준(%.1f) 초과 경험 %d", int(per["ok"].sum()), rules["acwr"]["flag"], int(per["flag"].sum()))
    return {"names": names, "summary": summary.assign(학교명=summary["학교"].map(school_name))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="이 데이터셋 키만 변환")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "hs_records.log", encoding="utf-8"), logging.StreamHandler()])
    cfg, datasets = hr.datasets_config()
    name_path = Path(cfg["name_map"])
    if ROOT in name_path.parents:
        raise SystemExit("선수 실명 대응표는 저장소 밖에만 둡니다 (config_kbsa.yaml의 name_map).")
    name_path.parent.mkdir(parents=True, exist_ok=True)
    maps = []
    for key, (d, rules) in datasets.items():
        if a.only and key != a.only:
            continue
        out = convert(key, cfg, {**d, "key": key}, rules)
        maps.append(out["names"].assign(dataset=key))
        print(out["summary"].to_string(index=False))
    if maps and not a.only:
        pd.concat(maps, ignore_index=True).to_csv(name_path, index=False, encoding="utf-8-sig")
        log.info("선수 실명 대응표 저장: %s", name_path)


if __name__ == "__main__":
    main()
