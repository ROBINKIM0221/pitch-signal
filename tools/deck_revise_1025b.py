"""발표자료 최종 수정 2 (2026-10-25): 표지에서 뺀 내용을 다른 쪽에, 4·9쪽 제목.
- 1쪽: PITCHSIGNAL 아래 서비스 한 줄(두 줄) 되살림
- 2쪽 ①단계: 규정 계산 설명 줄 대신 1,896구 훅
- 4쪽 제목 '기록에 없는 볼, 자체 개발 판독 모델로 읽다' / 9쪽 제목 '오경보는 설계값대로, 경보 뒤 부상은 2배'
    python -m tools.deck_revise_1025b <입력.pptx> <출력.pptx>
"""
from __future__ import annotations

import sys

from pptx import Presentation

from tools import build_deck as bd
from tools.deck_revise_1023 import shape, title


def s1(s):
    bd.text(s, 0.95, 4.25, 5.8, 0.9, [[bd.body("고교부터 프로까지,", 16, bd.WHITE, True)],
                                       [bd.body("투수의 누적 부하와 부상 위험 신호를 알려 줍니다", 16, bd.WHITE, True)]], line=1.3)


def s2(s):
    sh = next(x for x in s.shapes if x.has_text_frame and x.text_frame.text.startswith("2026 시즌 전국 고교 공식 경기 991경기"))
    p1 = sh.text_frame.paragraphs[1]
    for r in p1.runs[1:]:
        r._r.getparent().remove(r._r)
    p1.runs[0].text = "그 한 건의 투수는 시즌 29등판 1,896구"
    p1.runs[0].font.color.rgb = bd.INK; p1.runs[0].font.size = bd.Pt(12.5)
    p2 = sh.text_frame.add_paragraph()
    bd._font(p2.add_run(), bd.BODY, 12.5, bd.INK); p2.runs[0].text = "규정이 문제 삼은 날은 하루"


def main(src: str, out: str) -> None:
    prs = Presentation(src)
    sl = list(prs.slides)
    s1(sl[0]); s2(sl[1])
    title(sl[3], "기록에 없는 볼, 자체 개발 판독 모델로 읽다")
    title(sl[8], "오경보는 설계값대로, 경보 뒤 부상은 2배")
    shape(sl[8], 5).text_frame.paragraphs[0].runs[0].font.size = bd.Pt(40)
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
