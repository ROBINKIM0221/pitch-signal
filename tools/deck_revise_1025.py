"""발표자료 최종 수정 (2026-10-25, 사용자 검토 — 메모 C:/work/private/pitchsignal/발표_수정메모_2차.md 끝부분). 사용자가 저장한 파일 위에서.
- 1쪽: 숫자·설명 없이 이름만 — 투수 사진(오른쪽 꽉 채움) + 피치시그널 / PITCHSIGNAL / 이름·소속·메일·전화·사이트
- 3쪽: 선수 카드 캡처를 찢어진 프레임 없이 반듯하게, 더 크게
- 6쪽: 그림 안 설명 글을 빼고 슬라이드 글상자로
    python -m tools.deck_revise_1025 <입력.pptx> <출력.pptx> <투수사진> <전화번호>
"""
from __future__ import annotations

import sys

from PIL import Image
from pptx.enum.text import PP_ALIGN
from pptx import Presentation

from tools import build_deck as bd
from tools.deck_revise_1023 import drop, shape
from tools.deck_revise_1024 import DECK, PRIVATE

SCREEN = bd.SCREENS / "04b_ball_ratio.png"


def fill_picture(slide, path, x, y, w, h):
    """사진을 자르지 않고 늘리지도 않게 — 칸 비율에 맞춰 가운데를 남기고 가장자리를 잘라 채운다."""
    im = Image.open(path)
    pic = bd.picture(slide, path, x, y, w, h)
    want, have = h / w, im.height / im.width
    if have > want:                                       # 세로가 남음 → 위아래를 잘라 냄
        c = (1 - want / have) / 2; pic.crop_top = pic.crop_bottom = c
    else:
        c = (1 - have / want) / 2; pic.crop_left = pic.crop_right = c
    return pic


def s1(s, photo, phone):
    drop(s, 7, 8, 9, 10, 11, 12, 13)
    im = Image.open(photo)                                # 누끼 딴 투수(투명 배경): 바닥에 발이 닿게 오른쪽 아래에, 높이 7인치 (사용자 10/25 "누끼 따서")
    h = 7.0; w = h * im.width / im.height
    if w > 7.6:                                           # 여러 명 합친 넓은 그림은 폭으로 맞춤
        w = 7.6; h = w * im.height / im.width
    pic = bd.picture(s, photo, bd.SW - w - 0.2, bd.SH - h, w, h)
    tree = pic._element.getparent(); tree.remove(pic._element)
    tree.insert(tree.index(shape(s, 3)._element) + 1, pic._element)     # 글자 뒤로 (줄무늬 바로 위)
    h = shape(s, 4); h.left, h.top = bd.Inches(0.85), bd.Inches(0.5)
    h.text_frame.paragraphs[0].alignment = PP_ALIGN.LEFT
    t = shape(s, 5); t.left, t.top = bd.Inches(0.85), bd.Inches(1.9)
    e = shape(s, 6); e.left, e.top = bd.Inches(0.95), bd.Inches(3.1)
    bd.text(s, 0.9, 5.3, 5.8, 1.7, [[bd.body("김형준 · UNIST", 20, bd.WHITE, True)],
                                     [bd.body(f"robin1967@unist.ac.kr  ·  {phone}", 14, bd.SOFT)],
                                     [bd.body("robinkim0221.github.io/pitch-signal", 14, bd.BLUE)]], line=1.4)


def s3(s):
    drop(s, 15)
    w = 6.4
    pic = bd.picture(s, SCREEN, 6.55, 1.9, w, bd.fit(SCREEN, w))
    pic.line.color.rgb = bd.SOFT; pic.line.width = bd.Pt(0.75)


def s6(s):
    drop(s, 10, 11, 12)
    zoom, sc = PRIVATE / "raw_zoom.png", DECK / "pitch_scatter.png"
    bd.text(s, 0.45, 1.9, 8.5, 0.35, [[bd.body("원자료 그대로 — Baseball Savant 열 이름과 단위(mph, ft), 이 등판 92구 중 처음 16구 (열 119개 중 9개)", 11, bd.SOFT)]])
    bd.picture(s, zoom, 0.45, 2.3, 8.5)
    bd.text(s, 9.2, 1.9, 3.95, 0.35, [[bd.body("그날 92구의 릴리스 위치 (포수 쪽에서 봄)", 11, bd.SOFT, True)]])
    bd.picture(s, sc, 9.2, 2.3, 3.95)
    bd.text(s, 9.2, 2.3 + bd.fit(sc, 3.95) + 0.15, 3.95, 0.8, [[bd.body("Baseball Savant(MLB 공개 투구 기록)에서 내려받은 원자료", 10, bd.SOFT)],
                                                               [bd.body("Michael Soroka · 2025년 7월 4일 등판 92구 × 항목 119개", 10, bd.SOFT)]], line=1.2)
    bd.text(s, 0.45, 6.72, 8.5, 0.6, [[bd.body("KBO 구단도 같은 추적 장비(트랙맨)로 공마다 이 데이터를 갖고 있습니다", 12, bd.WHITE)],
                                      [bd.body("공개되지 않았을 뿐, 구단 안에서는 바로 쓸 수 있습니다", 12, bd.SOFT)]], line=1.15)   # 2026-10-25 사용자


def s7(s):
    """'나와 비교하면' 줄에 연구 출처 — 사용자 질문(어디 연구인지)에 답한 뒤 슬라이드에도 붙임. (PowerPoint가 저장하며 조각을 쪼개 두므로 문단을 새로 짠다)"""
    sh = next(x for x in s.shapes if x.has_text_frame and x.text_frame.text.startswith("나와 비교하면"))
    tf = sh.text_frame
    for p in tf.paragraphs[1:]:
        p._p.getparent().remove(p._p)
    p0 = tf.paragraphs[0]
    for r in p0.runs[1:]:
        r._r.getparent().remove(r._r)
    p0.runs[0].text = "나와 비교하면 — "
    bd._font(p0.add_run(), bd.BODY, 12.5, bd.INK); p0.runs[-1].text = "부상 직전 등판들에서 본인 구속이 떨어짐 (컬럼비아대 의대 2026, 팔꿈치 78명 · 어깨 27명)"
    sh.height = bd.Inches(0.7)


def main(src: str, out: str, photo: str, phone: str) -> None:
    prs = Presentation(src)
    sl = list(prs.slides)
    s1(sl[0], photo, phone); s3(sl[2]); s6(sl[5]); s7(sl[6])
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
    main(*sys.argv[1:5])
