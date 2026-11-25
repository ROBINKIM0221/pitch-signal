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
import json
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
SHEET_PITCHING = RAW / "sheet_pitching.csv"     # 공식 투수 기록표가 빈 경기를 기록지 투수 칸에서 옮겨 적은 줄 (실명이 있어 저장소 밖, 2026-11-02)


def sheet_pitching() -> dict[int, list[dict]]:
    """경기 → 옮겨 적은 투수 줄 (기록지 순서 = 등판 순서)."""
    if not SHEET_PITCHING.exists():
        return {}
    t = pd.read_csv(SHEET_PITCHING, encoding="utf-8-sig", dtype={"innings": str, "result": str})
    return {int(g): part.drop(columns="game_idx").to_dict("records") for g, part in t.groupby("game_idx", sort=False)}


def parse_games(game_ids: list[int], unreadable: dict[int, str] | None = None) -> pd.DataFrame:
    """unreadable을 주면 해석할 수 없는 기록 페이지의 경기를 거기에 적고 빼며(주간 갱신), 안 주면 멈춘다."""
    pages = {g: RAW / f"record_detail_{g}.html" for g in game_ids}
    missing = [g for g, p in pages.items() if not p.exists()]
    if missing:
        log.warning("기록 페이지가 없는 경기 %d개는 뺀다: %s", len(missing), missing[:10])
    games, flows, sheet, from_sheet = [], {}, sheet_pitching(), set()
    for g, p in pages.items():
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        try:
            game = kb.parse_record_detail(text, g)
        except ValueError as e:
            if unreadable is None:
                raise
            unreadable[g] = str(e)
            continue
        if hr.fill_from_sheet(game, sheet.get(g)):
            from_sheet.add(g)
        games.append(game)
        for key, flow in hr.flows_for_game(game, kb.parse_batting(text)).items():          # 등판 흐름 (상대 타격표의 타석을 투수에게 배정)
            flows[(g, *key)] = json.dumps(flow, ensure_ascii=False)
    rows = kb.games_to_rows(games)
    rows["flow"] = [flows.get((r.game_idx, r.team, r.name, r.number)) for r in rows.itertuples()]
    rows["sheet"] = rows["game_idx"].isin(from_sheet)
    if from_sheet:
        log.info("공식 투수 기록표가 비어 기록지 투수 칸에서 옮겨 적은 경기 %d: %s", len(from_sheet), sorted(from_sheet))
    log.info("등판 흐름 재구성: 등판 %d개 중 %d개 (%.1f%%)", len(rows), rows["flow"].notna().sum(), 100 * rows["flow"].notna().mean() if len(rows) else 0)
    return rows


def season_games(cfg: dict, d: dict) -> tuple[list[int], pd.Series, dict[str, str]]:
    """시즌 모드(전국): 경기 목록(games_csv)의 모든 경기와 대회 이름, 팀 → 권역(주말리그 참가 리그 기준, 없으면 '기타')."""
    games = pd.read_csv(ROOT / d.get("games_csv", cfg["games_csv"]), encoding="utf-8-sig")      # 데이터셋마다 경기 목록 (2026-10-16 연도 추가)
    region_of: dict[str, str] = {}
    for region, leagues in d["region_leagues"].items():
        for team in set(games.loc[games["lig_idx"].isin(leagues), ["team1", "team2"]].stack()):
            region_of.setdefault(team, region)
    pick = games.copy()
    comp = pd.Series([hr.competition_of(d, x) for x in pick["league"]], index=pick["game_idx"].to_numpy())
    return pick["game_idx"].tolist(), comp, region_of


def convert(key: str, cfg: dict, d: dict, rules: dict, skip: frozenset = frozenset()) -> dict | None:
    if d["mode"] == "tournament":
        ids, region_of = list(d["games"]), None
        comp = pd.Series(d["overrides"]["competitions"][0], index=ids)
    else:
        ids, comp, region_of = season_games(cfg, d)
    ids = [g for g in ids if g not in skip]
    live, unreadable = bool(d.get("live")), {}
    raw = hr.combine_stints(hr.mark_missing_detail(parse_games(ids, unreadable if live else None)))
    held = PROCESSED / f"hs_{key}_quarantine.csv"                # 뺀 경기 (주간 갱신 데이터셋만): 해석 못 한 기록 페이지, 입력 검사에 걸린 경기
    pages = pd.DataFrame([(g, "기록 페이지", why) for g, why in unreadable.items()], columns=["game_idx", "kind", "detail"])
    if not skip:
        if len(pages):
            log.warning("%s: 기록 페이지를 해석할 수 없는 경기 %d개를 뺀다: %s", key, len(pages), sorted(unreadable))
            pages.to_csv(held, index=False, encoding="utf-8-sig")
        else:
            held.unlink(missing_ok=True)
    if raw.empty:
        log.info("%s: 기록 페이지가 있는 경기가 없어 건너뜀", key)
        return None
    names = hr.name_map(raw)
    if region_of is not None:
        names["region"] = names["team"].map(region_of).fillna("기타")
        others = sorted(names.loc[names["region"] == "기타", "team"].unique())
        if others:
            log.info("주말리그에 없어 '기타' 권역으로 둔 팀 %d: %s", len(others), others)
    rules = {**rules, "schools": int(raw["team"].nunique())}
    rows = hr.input_rows(raw, names, comp, d.get("rounds"))
    problems = hs.problems(rows, rules)
    if len(problems) and live and d["mode"] == "season" and not skip:
        bad = pd.concat([pages, hr.problem_games(rows, problems)], ignore_index=True)
        bad.to_csv(held, index=False, encoding="utf-8-sig")
        log.warning("%s: 뺄 경기 %d개(입력 검사·기록 페이지)를 빼고 다시 만든다: %s", key, bad["game_idx"].nunique(), sorted(set(bad["game_idx"])))
        return convert(key, cfg, d, rules, skip=frozenset(int(g) for g in bad["game_idx"]))
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
    names.drop(columns="name").to_csv(PROCESSED / f"hs_{key}_names.csv", index=False, encoding="utf-8-sig")   # 학교 실명·권역·등번호 표기 (선수 실명 없음)
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
        log.info("ACWR 계산 가능 투수 %d, 기준(%.1f) 초과 경험 %d (만성 하한 %s구/주), 권역별 팀 수 %s", int(per["ok"].sum()), rules["acwr"]["flag"], int(per["flag"].sum()),
                 rules["acwr"].get("min_chronic", 0), names.drop_duplicates("team")["region"].value_counts().to_dict())
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
        d = hr.resolve_dataset(d)
        out = convert(key, cfg, {**d, "key": key}, rules) if d is not None else None
        if out is None:
            log.info("%s: 경기 목록이 아직 없거나 대회가 덜 끝나 건너뜀", key)
            continue
        maps.append(out["names"].assign(dataset=key))
        print(out["summary"].to_string(index=False))
    if maps:
        new = pd.concat(maps, ignore_index=True)
        if a.only and name_path.exists():       # 한 데이터셋만 다시 만들 때는 그 몫만 바꾼다 (안 바꾸면 새 투수로 밀린 코드에 옛 이름이 붙음, 2026-11-02)
            old = pd.read_csv(name_path, encoding="utf-8-sig")
            new = pd.concat([old[old["dataset"] != a.only], new], ignore_index=True)
        new.to_csv(name_path, index=False, encoding="utf-8-sig")
        log.info("선수 실명 대응표 저장: %s", name_path)


if __name__ == "__main__":
    main()
