"""발표자료 10쪽 '대회 운영본부' 줄에 2027 경기도 전국체전 (2026-10-25, 공모전 소개 영상이 2027 전국체전을 바라본다는 사용자 확인 뒤).
    python -m tools.deck_revise_1025c <입력.pptx> <출력.pptx>
"""
from __future__ import annotations

import sys

from pptx import Presentation

from tools.deck_revise_1023 import set_text

LINE = "2027 경기도 전국체전에서 운영본부와 각 팀이 같은 화면으로 규정 위반과 누적 부하 확인 — 2025·2026 전국체전 기록으로 이미 운영해 봄 · 주말리그·전국대회, 대학·중학·리틀야구에도"


def main(src: str, out: str) -> None:
    prs = Presentation(src)
    s = prs.slides[9]
    sh = next(x for x in s.shapes if x.has_text_frame and x.text_frame.text.startswith("운영본부와 각 팀이"))
    set_text(sh, LINE)
    for p in sh.text_frame.paragraphs:
        p._p.get_or_add_pPr().set("eaLnBrk", "0")
        for run in p.runs:
            run._r.get_or_add_rPr().set("lang", "ko-KR")
    prs.save(out)
    print("저장:", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
