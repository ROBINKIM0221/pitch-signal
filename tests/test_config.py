"""설정 읽기 테스트. 실행: python -m pytest -q"""
from src.common.config import load_config


def write(path, text):
    path.write_text(text, encoding="utf-8")


def test_reads_repo_config():
    cfg = load_config()
    assert cfg["data"]["split"]["sealed"] == [2026]


def test_works_without_calibrated_file(tmp_path):
    write(tmp_path / "config.yaml", "seed: 1\nmonitor: {lambdas: [0.1, 0.2]}\n")
    assert load_config(tmp_path) == {"seed": 1, "monitor": {"lambdas": [0.1, 0.2]}}


def test_calibrated_wins_and_keeps_other_keys(tmp_path):
    write(tmp_path / "config.yaml", "seed: 1\nmonitor: {lambdas: [0.1, 0.2], t2_alpha: 0.001}\n")
    write(tmp_path / "config_calibrated.yaml", "monitor: {final_lambda: 0.2, t2_alpha: 0.0005}\n")
    cfg = load_config(tmp_path)
    assert cfg["monitor"] == {"lambdas": [0.1, 0.2], "t2_alpha": 0.0005, "final_lambda": 0.2}
    assert cfg["seed"] == 1
