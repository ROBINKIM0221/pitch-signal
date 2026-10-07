"""전국체전 기록 변환 (화면 3의 실제 입력). 설정은 config_kbsa.yaml.

data/raw/kbsa/record_detail_<game_idx>.html (KBSA 기록실 경기 기록, 1회 수집) →
  <name_map>                                 실명 ↔ 가명 대응표 (저장소 밖, config의 name_map 경로)
  data/processed/hs_tournament_rows.parquet  가명 등판표 (고교 모듈 입력 열 + 상대·등판 구분·라운드·휴식일 주석)
  data/processed/hs_tournament_daily.parquet 투수별 하루 단위 값 (highschool.daily_table)
  data/processed/hs_tournament_violations.csv 규정 위반·판정 불가 목록
  reports/tables/hs_tournament_summary.csv   학교별 요약 (가명)

사용 예:
    python -m src.17_kbsa_tournament
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.common import highschool as hs
from src.common import kbsa_boxscore as kb
from src.common import tournament as tn
from src.common.config import ROOT

RAW = ROOT / "data" / "raw" / "kbsa"
PROCESSED = ROOT / "data" / "processed"
TABLES = ROOT / "reports" / "tables"
log = logging.getLogger("pitchsignal.tournament")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "tournament.log", encoding="utf-8"), logging.StreamHandler()])
    t, rules = tn.tournament_config()
    pages = [RAW / f"record_detail_{g}.html" for g in t["games"]]
    missing = [p.name for p in pages if not p.exists()]
    if missing:
        raise SystemExit(f"수집한 경기 기록 페이지가 없습니다: {', '.join(missing)} (data/raw/kbsa/)")
    games = [kb.parse_record_detail(p.read_text(encoding="utf-8"), g) for p, g in zip(pages, t["games"])]
    raw = tn.combine_stints(tn.mark_missing_detail(kb.games_to_rows(games)))
    names = tn.name_map(raw, t["seed"])
    rows = tn.input_rows(raw, names, t["short"], t["rounds"])

    problems = hs.problems(rows, rules)
    if len(problems):
        print(problems.to_string(index=False))
        raise SystemExit("변환한 표가 입력 검사를 통과하지 못했습니다.")
    daily = hs.daily_table(rows, rules)
    violated = hs.violations(rows, daily, rules)
    outings = tn.annotate_outings(rows, rules["kbsa"])
    summary = hs.summary(daily, violated)

    name_path = Path(t["name_map"])
    if ROOT in name_path.parents:
        raise SystemExit("실명 대응표는 저장소 밖에만 둡니다 (config_kbsa.yaml의 name_map).")
    name_path.parent.mkdir(parents=True, exist_ok=True)
    names.to_csv(name_path, index=False, encoding="utf-8-sig")
    outings.to_parquet(PROCESSED / "hs_tournament_rows.parquet", compression="zstd", index=False)
    daily.to_parquet(PROCESSED / "hs_tournament_daily.parquet", compression="zstd", index=False)
    violated.to_csv(PROCESSED / "hs_tournament_violations.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(TABLES / "hs_tournament_summary.csv", index=False, encoding="utf-8-sig")

    no_detail = sorted(int(g) for g in rows.loc[~rows["detail"], "game_no"].unique())
    log.info("%s: 경기 %d(상세 기록 없는 경기 %s), 학교 %d, 투수 %d, 등판 %d(두 번 등판 합친 줄 %d), 투구 수 모르는 등판 %d",
             t["name"], rows["game_no"].nunique(), no_detail or "없음", rows["school"].nunique(), rows["pitcher"].nunique(), len(rows),
             int((rows["stints"] > 1).sum()), int(rows["pitches"].isna().sum()))
    log.info("규정 위반·판정 불가: %s", violated["rule"].value_counts().to_dict() or "없음")
    second = outings[outings["gap_days"].notna()]
    log.info("두 번째 이후 등판 %d: 연투(사이에 쉰 날 0) %d, 최소 휴식만 채우고 등판 %d, 휴식 부족 %d",
             len(second), int((second["gap_days"] == 0).sum()), int((second["min_rest_exact"] == True).sum()), int((second["rest_ok"] == False).sum()))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
