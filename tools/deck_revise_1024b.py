"""발표자료 2차 수정 뒤 사용자 검토 반영 (2026-10-24 밤). 사용자가 직접 고쳐 저장한 파일 위에서 6·7·9쪽만 고친다.
- 6쪽: 엑셀 캡처 빼고 원자료 표(16구)를 크게, 점 그림과 함께 프레임 없이
- 7쪽: 하늘색 큰 숫자(7%·5등판) 대신 글 두 줄, 표 '공이 적은 등판' → '투구 수 적은 등판'
- 9쪽: '2배' 카드 → 경보 유무별 '30일 내 팔 부상 IL' 비율 표 (사용자: '아님' 열은 빼기)
    python -m tools.deck_revise_1024b <입력.pptx> <출력.pptx>
"""
from __future__ import annotations

import sys

from pptx import Presentation
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

from tools import build_deck as bd
from tools.deck_revise_1023 import drop, set_text, shape
from tools.deck_revise_1024 import DECK, PRIVATE, rule


def s6(s):
    drop(s, 10, 11, 12, 13)
    zoom = PRIVATE / "raw_zoom.png"
    w = 8.5; h = bd.fit(zoom, w)
    bd.picture(s, zoom, 0.45, 1.95 + max(0, (4.7 - h) / 2), w)
    sc = DECK / "pitch_scatter.png"
    bd.picture(s, sc, 9.2, 1.95, 3.95)
    bd.text(s, 9.2, 1.95 + bd.fit(sc, 3.95) + 0.15, 3.95, 0.8, [[bd.body("Baseball Savant(MLB 공개 투구 기록)에서 내려받은 원자료 그대로", 10, bd.SOFT)],
                                                                [bd.body("Michael Soroka · 2025년 7월 4일 등판 92구 × 항목 119개", 10, bd.SOFT)]], line=1.2)


def s7(s):
    drop(s, 10, 11, 12, 13)
    X = 7.95
    for y, head, desc in ((2.2, "선수끼리 비교하면 — ", "구속·체중·나이는 팔꿈치 수술과 7%만 관련 (2016년 MLB 투수 연구)"),
                          (2.95, "나와 비교하면 — ", "부상 직전 등판들에서 본인 구속이 떨어짐 (팔꿈치 78명 · 어깨 27명 연구)")):
        bd.text(s, X, y, 4.9, 0.7, [[bd.body(head, 12.5, bd.INK, True), bd.body(desc, 12.5, bd.INK)]], anchor=MSO_ANCHOR.MIDDLE, line=1.15)
    set_text(shape(s, 23), "투구 수 적은 등판")
    set_text(shape(s, 20), "시즌 초 평균 고정")
    set_text(shape(s, 25), "적을수록 덜 반영")
    for sid in (15, 19, 23, 27):
        shape(s, sid).width = bd.Inches(1.5)
    for sid in (16, 20, 24, 28):
        sh = shape(s, sid); sh.left, sh.width = bd.Inches(9.45), bd.Inches(1.5)


def s9(s):
    drop(s, 10, 11, 12)
    X, y = 7.95, 4.0
    bd.text(s, X + 2.6, y, 2.25, 0.35, [[bd.body("30일 내 팔 부상 IL", 12.5, bd.INK, True)]], anchor=MSO_ANCHOR.MIDDLE)
    rule(s, X, y + 0.36, 4.9, bd.INK)
    y += 0.4
    for label, val, color in (("경보 울린 등판 (200개)", "10.5% (21개)", bd.BLUE), ("경보 없던 등판 (20,088개)", "4.8% (972개)", bd.INK)):
        bd.text(s, X, y, 2.6, 0.5, [[bd.body(label, 12, bd.INK)]], anchor=MSO_ANCHOR.MIDDLE)
        bd.text(s, X + 2.6, y, 2.25, 0.5, [[bd.body(val, 17, color, True)]], anchor=MSO_ANCHOR.MIDDLE)
        y += 0.5
        rule(s, X, y, 4.9)
    bd.text(s, X, y + 0.12, 4.9, 0.75, [[bd.body("→ 경보 울린 등판 쪽이 2.2배 (2026 시즌도 2.0배)", 11.5, bd.INK)],
                                        [bd.body("경보는 부상 판정이 아니라, 점검을 시작하라는 신호", 11.5, bd.MUTED)]], line=1.25)


def main(src: str, out: str) -> None:
    prs = Presentation(src)
    sl = list(prs.slides)
    s6(sl[5]); s7(sl[6]); s9(sl[8])
    for s in sl:
        for sh in s.shapes:
            if sh.has_text_frame:
                for p in sh.text_frame.paragraphs:
                    p._p.get_or_add_pPr().set("eaLnBrk", "0")
                    for run in p.runs:
                        run._r.get_or_add_rPr().set("lang", "ko-KR")
    prs.save(out)
    print("저장:", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
