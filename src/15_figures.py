"""제안서·발표용 최종 그림 (단계 11.3). reports/figures/final/*.png와 captions.md를 만든다.

사용 예:
    python -m src.15_figures
"""
from __future__ import annotations

import logging

from src.common import figures as fg

log = logging.getLogger("pitchsignal.figures")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    names = fg.draw_all(fg.FINAL)
    for name in names:
        log.info("저장: %s", fg.FINAL / name)
    if "06_highschool.png" not in names:
        log.info("⑥ 고교 그림은 건너뜀: 대시보드 고교 자료가 아직 가상(meta.json synthetic)")
    log.info("캡션: %s", fg.FINAL / "captions.md")


if __name__ == "__main__":
    main()
