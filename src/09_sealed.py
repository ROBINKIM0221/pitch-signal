"""봉인 평가 (단계 9.2): 2026 분할을 단 한 번 평가한다. 계산은 08_evaluate --split val과 같다(src/common/evaluation.evaluate_split).

    python -m src.09_sealed --dry-run   # 세 가지 사전 점검만 (FROZEN, 설정 해시, 기존 결과 없음)
    python -m src.09_sealed             # 점검을 모두 통과하면 실행. 결과는 reports/sealed/, 로그 reports/logs/sealed.log

실행 뒤에는 reports/sealed/sealed_results.csv가 있으므로 다시 실행되지 않는다.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
from datetime import datetime

import pandas as pd

from src.common import sealed
from src.common.config import ROOT, load_config
from src.common.evaluation import evaluate_split

SEALED = ROOT / "reports" / "sealed"
log = logging.getLogger("pitchsignal.sealed")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="사전 점검만 하고 실행하지 않음")
    a = ap.parse_args()
    (ROOT / "reports" / "logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", handlers=[
        logging.FileHandler(ROOT / "reports" / "logs" / "sealed.log", encoding="utf-8"), logging.StreamHandler()])
    problems = sealed.preflight(ROOT)
    for p in problems:
        log.error("실행 불가: %s", p)
    if problems:
        raise SystemExit(1)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    log.info("사전 점검 통과. 커밋 %s%s, config.yaml %s, config_calibrated.yaml %s", commit[:12], " (커밋 안 한 변경 있음)" if dirty else "",
             sealed.file_hash(ROOT / "config.yaml")[:12], sealed.file_hash(ROOT / "config_calibrated.yaml")[:12])
    if a.dry_run:
        print("dry-run: 세 조건 모두 통과. 실행하려면 --dry-run 없이 다시 호출.")
        return

    cfg = load_config()
    SEALED.mkdir(parents=True, exist_ok=True)
    started = datetime.now()
    log.info("봉인 평가 시작 %s (2026 시즌, 단 한 번)", started.strftime("%Y-%m-%d %H:%M:%S"))
    evaluate_split(cfg, "sealed", tables=SEALED, figures=SEALED)
    far = pd.read_csv(SEALED / "sealed_false_alarms.csv", encoding="utf-8-sig")
    verdict = sealed.h3_verdict(far, 100 / cfg["monitor"]["arl0_target"])
    tests = pd.read_csv(SEALED / "sealed_tests.csv", encoding="utf-8-sig")
    h3 = {"test": "H3 봉인 실측 오경보 ≤ 설계값의 2배 (두 신호 모두)", "value": max(verdict["구속 하락 신호"][0], verdict["폼 변화 신호"][0]),
          "supported": verdict["supported"]}
    pd.concat([tests, pd.DataFrame([h3])], ignore_index=True).to_csv(SEALED / "sealed_tests.csv", index=False, encoding="utf-8-sig")
    (SEALED / "run_info.txt").write_text(
        f"실행 시각: {started:%Y-%m-%d %H:%M:%S} ~ {datetime.now():%H:%M:%S}\n커밋: {commit}\n커밋 안 한 변경: {'있음' if dirty else '없음'}\n"
        f"config.yaml SHA-256: {sealed.file_hash(ROOT / 'config.yaml')}\nconfig_calibrated.yaml SHA-256: {sealed.file_hash(ROOT / 'config_calibrated.yaml')}\n"
        f"H3: 구속 하락 신호 {verdict['구속 하락 신호'][0]:.3f}/100 ({'통과' if verdict['구속 하락 신호'][1] else '초과'}), "
        f"폼 변화 신호 {verdict['폼 변화 신호'][0]:.3f}/100 ({'통과' if verdict['폼 변화 신호'][1] else '초과'}) → {'지지' if verdict['supported'] else '지지 안 됨'}\n",
        encoding="utf-8")
    log.info("H3 판정: 구속 %.3f/100, 폼 변화 %.3f/100 → %s", verdict["구속 하락 신호"][0], verdict["폼 변화 신호"][0], "지지" if verdict["supported"] else "지지 안 됨")
    log.info("봉인 평가 끝. 결과 %s", SEALED)


if __name__ == "__main__":
    main()
