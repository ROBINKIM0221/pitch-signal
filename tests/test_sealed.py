"""봉인 평가 사전 점검 테스트 (단계 9.1). 실행: python -m pytest -q tests/test_sealed.py"""
import hashlib
from pathlib import Path

import pandas as pd

from src.common import sealed


def make_root(tmp_path: Path, frozen=True, hashes_ok=True, existing=False) -> Path:
    (tmp_path / "docs").mkdir(); (tmp_path / "reports" / "sealed").mkdir(parents=True)
    (tmp_path / "config.yaml").write_text("a: 1\n", encoding="utf-8")
    (tmp_path / "config_calibrated.yaml").write_text("b: 2\n", encoding="utf-8")
    h1 = hashlib.sha256((tmp_path / "config.yaml").read_bytes()).hexdigest()
    h2 = hashlib.sha256((tmp_path / "config_calibrated.yaml").read_bytes()).hexdigest()
    if not hashes_ok:
        h2 = "0" * 64
    plan = ("FROZEN: true\n" if frozen else "FROZEN: false\n") + f"- 설정 파일 해시 (`config.yaml` SHA-256): {h1}\n- 개발셋 확정값 파일 해시 (`config_calibrated.yaml` SHA-256): {h2}\n"
    (tmp_path / "docs" / "eval_plan.md").write_text(plan, encoding="utf-8")
    if existing:
        (tmp_path / "reports" / "sealed" / "sealed_results.csv").write_text("x\n", encoding="utf-8")
    return tmp_path


def test_preflight_passes_when_frozen_hashes_match_and_no_previous_result(tmp_path):
    assert sealed.preflight(make_root(tmp_path)) == []


def test_preflight_names_each_failed_condition(tmp_path):
    problems = sealed.preflight(make_root(tmp_path, frozen=False, hashes_ok=False, existing=True))
    assert len(problems) == 3
    assert any("FROZEN" in p for p in problems) and any("config_calibrated.yaml" in p for p in problems) and any("sealed_results.csv" in p for p in problems)


def test_plan_hashes_reads_the_two_sha256_values_from_the_plan(tmp_path):
    root = make_root(tmp_path)
    hashes = sealed.plan_hashes(root / "docs" / "eval_plan.md")
    assert set(hashes) == {"config.yaml", "config_calibrated.yaml"} and all(len(v) == 64 for v in hashes.values())


def test_h3_verdict_checks_both_signals_against_twice_the_design_rate():
    far = pd.DataFrame({"role": ["all", "all", "SP"], "season": ["all", "all", "all"], "per100": [1.4, 2.3, 0.9],
                        "method": ["구속 하락 신호", "폼 변화 신호", "구속 하락 신호"]})
    out = sealed.h3_verdict(far, design_per100=1.0)
    assert out["구속 하락 신호"] == (1.4, True) and out["폼 변화 신호"] == (2.3, False)
    assert out["supported"] is False
