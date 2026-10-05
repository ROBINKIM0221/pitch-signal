"""설정 읽기. 모든 모듈은 load_config()로 설정을 읽는다 (저장소 규칙 3)."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def _merge(base: dict, over: dict) -> dict:
    """over의 값을 base에 덮어쓴다. 양쪽 다 dict인 키는 안쪽까지 합친다."""
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(root: Path | str = ROOT) -> dict:
    """config.yaml을 읽고, config_calibrated.yaml이 있으면 그 값을 덮어써서 돌려준다."""
    root = Path(root)
    cfg = yaml.safe_load((root / "config.yaml").read_text(encoding="utf-8"))
    calibrated = root / "config_calibrated.yaml"
    if calibrated.exists():
        cfg = _merge(cfg, yaml.safe_load(calibrated.read_text(encoding="utf-8")) or {})
    return cfg


def save_calibrated(updates: dict, root: Path | str = ROOT) -> None:
    """개발셋에서 규칙대로 정한 값을 config_calibrated.yaml에 더한다. 이미 있던 값은 남기고 config.yaml은 건드리지 않는다."""
    path = Path(root) / "config_calibrated.yaml"
    current = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    path.write_text(yaml.safe_dump(_merge(current or {}, updates), allow_unicode=True, sort_keys=False),
                    encoding="utf-8", newline="\n")
