"""봉인 평가(2026)의 사전 점검과 판정 (단계 9). 계산 자체는 evaluation.evaluate_split이 한다.

점검 세 가지: ① docs/eval_plan.md 첫 줄이 FROZEN: true ② config.yaml·config_calibrated.yaml의 SHA-256이 평가 계획서에 적힌 값과 같음
③ reports/sealed/sealed_results.csv가 아직 없음(한 번만 실행). 하나라도 걸리면 실행하지 않는다.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pandas as pd

HASH_LINE = re.compile(r"`(config(?:_calibrated)?\.yaml)` SHA-256\):\s*([0-9a-f]{64})")


def plan_hashes(plan_path: Path) -> dict[str, str]:
    """평가 계획서에 적힌 두 설정 파일의 해시. 변경 기록에 새 값이 있으면 마지막 값을 쓴다."""
    found: dict[str, str] = {}
    for name, value in HASH_LINE.findall(plan_path.read_text(encoding="utf-8")):
        found[name] = value
    return found


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight(root: Path) -> list[str]:
    """실행을 막는 이유 목록. 비어 있으면 실행해도 된다."""
    problems = []
    plan = root / "docs" / "eval_plan.md"
    if plan.read_text(encoding="utf-8").splitlines()[0].strip() != "FROZEN: true":
        problems.append("docs/eval_plan.md 첫 줄이 FROZEN: true 가 아닙니다")
    expected = plan_hashes(plan)
    for name in ("config.yaml", "config_calibrated.yaml"):
        actual = file_hash(root / name)
        if expected.get(name) != actual:
            problems.append(f"{name} 해시가 평가 계획서와 다릅니다 (계획서 {expected.get(name, '없음')[:12]}… / 지금 {actual[:12]}…)")
    if (root / "reports" / "sealed" / "sealed_results.csv").exists():
        problems.append("reports/sealed/sealed_results.csv 가 이미 있습니다 — 봉인 평가는 한 번만 실행합니다")
    return problems


def h3_verdict(false_alarms: pd.DataFrame, design_per100: float) -> dict:
    """H3: 두 신호 각각 전체(역할 all·시즌 all) 실측 오경보가 설계값의 2배 이내."""
    out: dict = {}
    for method in ("구속 하락 신호", "폼 변화 신호"):
        row = false_alarms[(false_alarms["method"] == method) & (false_alarms["role"] == "all") & (false_alarms["season"] == "all")]
        per100 = float(row["per100"].iloc[0])
        out[method] = (per100, per100 <= 2 * design_per100)
    out["supported"] = all(v[1] for k, v in out.items() if k != "supported")
    return out
