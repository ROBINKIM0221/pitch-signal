"""발표자료 2차 수정 (2026-10-24, 사용자와 10장을 다시 본 뒤 한 번에 — 메모 C:/work/private/pitchsignal/발표_수정메모_2차.md).
1차 수정과 영상 삽입이 끝난 제출물 파일을 그대로 열어 고친다 (영상·포함 글꼴은 python-pptx가 그대로 보존하고, 글꼴은 build_deck.finalize가 다시 포함).
    python -m tools.deck_revise_1024 <입력.pptx> <출력.pptx>
먼저 만들어 둘 그림: tools.deck_assets(false_alarm_case·people_row·opcurve), tools.deck_pitch_data(raw csv·raw_zoom·scatter) + 엑셀 캡처(raw_excel.png), 2026 전국체전 달력(tour_2026.png).
"""
from __future__ import annotations

import sys

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN

from tools import build_deck as bd
from tools.deck_revise_1023 import card, drop, set_text, shape, title

DECK, PRIVATE = bd.DECK, bd.PRIVATE / "deck"
NAVY = bd.RGBColor(0x1F, 0x4E, 0x8C)


def set_lines(sh, lines):
    """문단마다 첫 조각 서식을 살려 글만 바꾼다 (문단 수는 lines에 맞춤)."""
    tf = sh.text_frame
    for p in tf.paragraphs[len(lines):]:
        p._p.getparent().remove(p._p)
    for p, t in zip(tf.paragraphs, lines):
        for r in p.runs[1:]:
            r._r.getparent().remove(r._r)
        p.runs[0].text = t


def _flat(slide, kind, x, y, w, h, color):
    shp = slide.shapes.add_shape(kind, bd.Inches(x), bd.Inches(y), bd.Inches(w), bd.Inches(h))
    shp.fill.solid(); shp.fill.fore_color.rgb = color; shp.line.fill.background(); shp.shadow.inherit = False
    return shp


def rule(slide, x, y, w, color=bd.SOFT):
    _flat(slide, MSO_SHAPE.RECTANGLE, x, y, w, 0.012, color)


def s1(s):
    set_lines(shape(s, 7), ["고교부터 프로까지,", "투수의 누적 부하와 부상 위험 신호를 알려 줍니다"])     # '혹사'는 2쪽과 같이 쓰지 않음
    set_text(shape(s, 11), "2026년 한 고교 투수가 29번 등판해 던진 공")


def s2(s):
    title(s, "규정의 한계")
    drop(s, 6, 7, 8, 9, 10, 11, 12, 14, 15)
    for x, head, body in ((0.6, "지금 규정 (대한야구소프트볼협회)", "하루 105구 · 공 수에 따라 의무 휴식 1~4일 · 3일 연속 등판 금지"),
                          (6.78, "규정이 못 보는 것: 며칠에 걸쳐 쌓이는 양", "2026 전국체전 우승팀 투수 — 7일 동안 257구 (59→60→34→104구), 규정 위반 0")):
        bd.picture(s, DECK / "box_wide.png", x, 1.62, 5.95, 1.62)
        bd.text(s, x + 0.35, 1.8, 5.25, 1.26, [[bd.body(head, 15, bd.WHITE, True)], [bd.body(body, 13, bd.WHITE)]], anchor=MSO_ANCHOR.MIDDLE, line=1.2, after=4)
    Y, W, cols = 3.5, 3.75, (0.6, 4.95, 9.3)
    for x, n, head in zip(cols, ("01", "02", "03"), ("규정 위반 1건", "누적 부하 기준 두 단계", "2026 시즌에 적용하면")):
        bd.circle(s, x, Y, 0.7, n, size=18)
        bd.text(s, x + 0.85, Y, W - 0.85, 0.7, [[bd.body(head, 16, bd.INK, True)]], anchor=MSO_ANCHOR.MIDDLE)
    for x in (4.42, 8.77):
        _flat(s, MSO_SHAPE.RIGHT_ARROW, x, Y + 1.25, 0.45, 0.5, bd.RGBColor(0xBE, 0xE0, 0xF8))
    x = cols[0]
    bd.text(s, x, Y + 0.95, W, 1.4, [[bd.body("2026 시즌 전국 고교 공식 경기 991경기 · 7,078등판", 12.5, bd.INK)],
                                     [bd.body("기록을 규정(105구 · 의무 휴식 · 3일 연속)에 맞춰 계산한 결과", 12, bd.MUTED)]], line=1.2, after=4)
    x = cols[1]
    for i, (lv, color, rule_t, img, who) in enumerate((("주의", bd.BLUE, "7일 120구 · 3일 내 두 경기 70구", "people_2of10.png", "2025 시즌 투수 10명 중 2명이 넘은 선"),
                                                        ("높음", NAVY, "7일 150구 · 3일 내 두 경기 100구", "people_1of10.png", "10명 중 1명만 넘은 선"))):
        y = Y + 0.95 + i * 0.85
        bd.text(s, x, y, W, 0.3, [[bd.body(lv, 13, color, True), bd.body("  " + rule_t, 12.5, bd.INK)]])
        bd.picture(s, DECK / img, x, y + 0.36, 2.2, 0.26)
        bd.text(s, x + 2.3, y + 0.33, W - 2.3, 0.32, [[bd.body(who, 10.5, bd.MUTED)]], anchor=MSO_ANCHOR.MIDDLE)
    bd.text(s, x, Y + 2.7, W, 0.3, [[bd.body("기준은 2025 시즌 전국 고교 투구량으로 정해 2026에 적용", 10.5, bd.MUTED)]])
    x = cols[2]
    bd.text(s, x, Y + 0.9, 1.9, 0.9, [[("155", bd.BRUSH, 40, bd.BLUE), ("명", bd.TITLE, 22, bd.BLUE)]], anchor=MSO_ANCHOR.MIDDLE)
    bd.text(s, x + 1.95, Y + 0.95, W - 1.95, 0.85, [[bd.body("규정 위반 없이 '높음'", 14, bd.INK, True)], [bd.body("주의까지 272명", 13, bd.INK)]], anchor=MSO_ANCHOR.MIDDLE, line=1.2)
    bd.text(s, x, Y + 1.95, W, 0.6, [[bd.body("규정이 보지 못하는 누적 부하", 12.5, bd.MUTED)], [bd.body("따로 살펴봐야 할 투수", 12.5, bd.MUTED)]], line=1.2)
    bd.text(s, 0.6, 6.85, 12.2, 0.4, [[bd.body("자료: 대한야구소프트볼협회(KBSA) 기록실 — 2026 전국 고교 공식 경기 991경기 · 2025 시즌 투수 1,024명 (피치시그널 집계)", 11, bd.MUTED)]])


def s3(s):
    for sid, t in ((8, "경기별 볼 비율로 내 제구 흐름 확인 · 이닝별 투구로 경기 복기와 약점 파악"),
                   (11, "오늘 누가 몇 구까지 던질 수 있는지 · 팀 투수 누적 부하 관리 · 상대 투수의 볼 비율과 이닝별 흐름을 작전에"),
                   (14, "공식 기록에 없는 볼·스트라이크 비율과 경기 운영 능력 · 경기마다 제구가 얼마나 일정한지(기복) · 고교 시절 사용량 이력")):
        sh = shape(s, sid); set_text(sh, t); sh.width = bd.Inches(4.5); sh.height = bd.Inches(0.95)
        sh.text_frame.paragraphs[0].runs[0].font.size = bd.Pt(14)
    for sid in (7, 10, 13):
        shape(s, sid).width = bd.Inches(4.5)
    sh = shape(s, 13); set_text(sh, "프로 구단 스카우터 · 대학 감독"); sh.text_frame.paragraphs[0].runs[0].font.size = bd.Pt(19)
    pic = shape(s, 15)
    ratio = pic.height / pic.width
    pic.left, pic.top, pic.width = bd.Inches(6.65), bd.Inches(1.75), bd.Inches(6.3)
    pic.height = int(pic.width * ratio)


def s4(s):
    set_text(shape(s, 13), "읽은 공 수가 공식 투구 수와 맞은 등판 비율 (2026, 40구 이상)")
    set_text(shape(s, 16), "중계 영상의 공 5,348개 볼카운트와 비교한 볼 비율 차이, 평균 (2025)")
    for sid in (10, 13, 16):
        sh = shape(s, sid); sh.height = bd.Inches(0.6); sh.text_frame.paragraphs[0].runs[0].font.size = bd.Pt(12.5)


def video_caption(s, t):
    bd.text(s, 4.2, 0.3, 4.93, 0.3, [[bd.body(t, 10, bd.MUTED)]], align=PP_ALIGN.CENTER)


def s6(s):
    drop(s, 5, 10)                                        # X 붓자국('없다'로 읽힘)과 가공한 표 그림
    set_lines(shape(s, 9), ["고교 기록은 투구 수와 볼·스트라이크까지", "프로 구장은 공 하나하나의 구속과 폼까지 추적합니다"])
    bd.picture(s, bd.framed("raw_excel", PRIVATE / "raw_excel.png", private=True), 0.45, 1.8, 8.0)
    sc = bd.framed("pitch_scatter", DECK / "pitch_scatter.png")
    bd.picture(s, sc, 8.75, 1.8, 4.15)
    bd.picture(s, bd.framed("raw_zoom", PRIVATE / "raw_zoom.png", angle=-1.5, private=True), 2.3, 4.95, 6.0)
    bd.text(s, 8.75, 1.8 + bd.fit(sc, 4.15) + 0.1, 4.15, 0.8, [[bd.body("Baseball Savant(MLB 공개 투구 기록)에서 내려받은 원자료 그대로", 10, bd.SOFT)],
                                                                [bd.body("Michael Soroka · 2025년 7월 4일 등판 92구 × 항목 119개", 10, bd.SOFT)]], line=1.2)


def s7(s):
    drop(s, 6, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18)
    bd.picture(s, bd.framed("false_alarm_case", DECK / "false_alarm_case.png"), 0.35, 1.6, 7.35)
    set_text(shape(s, 7), "부상 없던 Juan Mejia(2026, 불펜): 1마일 규칙 20번 → 피치시그널 0번")
    X = 7.95
    for y, num, unit, head, desc in ((2.15, "7", "%", "선수끼리 비교", "구속·체중·나이로는 팔꿈치 수술의 7%만 설명"),
                                     (2.95, "5", "등판", "나와 비교", "부상 직전 5등판에 본인 구속 하락 (팔꿈치 78명 · 어깨 27명 연구)")):
        bd.text(s, X, y, 1.3, 0.72, [[(num, bd.BRUSH, 30, bd.BLUE), (unit, bd.TITLE, 15, bd.BLUE)]], anchor=MSO_ANCHOR.MIDDLE)
        bd.text(s, X + 1.35, y, 3.55, 0.72, [[bd.body(head + " — ", 12.5, bd.INK, True), bd.body(desc, 12.5, bd.INK)]], anchor=MSO_ANCHOR.MIDDLE, line=1.15)
    bd.text(s, X, 3.85, 4.9, 0.5, [[("1마일 규칙과 다른 점", bd.TITLE, 20, bd.INK)]])
    cx, cw, y = (X, X + 1.35, X + 3.0), (1.3, 1.6, 1.9), 4.4
    for j, (t, c) in enumerate((("", bd.INK), ("1마일 규칙", bd.INK), ("피치시그널", bd.BLUE))):
        bd.text(s, cx[j], y, cw[j], 0.35, [[bd.body(t, 12.5, c, True)]], anchor=MSO_ANCHOR.MIDDLE)
    rule(s, X, y + 0.36, 4.9, bd.INK)
    y += 0.4
    for row in (("평소", "시즌 초 평균에 고정", "등판마다 새로 계산"), ("공이 적은 등판", "똑같이 판단", "공이 적을수록 덜 반영"), ("보는 범위", "그 등판 하나", "최근 등판을 함께")):
        for j, t in enumerate(row):
            bd.text(s, cx[j], y, cw[j], 0.42, [[bd.body(t, 11.5, bd.INK, j == 0)]], anchor=MSO_ANCHOR.MIDDLE)
        y += 0.42
        rule(s, X, y - 0.02, 4.9)
    bd.text(s, X, y + 0.08, 4.9, 0.62, [[bd.body("→ 다치지 않은 투수에게는 100등판에 1번 울리도록 맞춤 — 2021~2023 시즌으로 맞추고, 다른 시즌에서 확인 (9쪽)", 11.5, bd.INK)]], line=1.2)
    bd.text(s, 0.6, 6.85, 12.2, 0.5, [[bd.body("1마일 규칙: FanGraphs(Petti, 2013) — 전해 4월보다 1마일(1.6km/h) 이상 떨어진 투수의 팔 부상률 11% vs 4%. 여기서는 시즌 초 평균에 적용 · 자료: MLB 2021~2026 공개 투구 기록", 9.5, bd.MUTED)]])


def s9(s):
    title(s, "경보는 설계한 만큼만 울리고, 울린 뒤엔 부상이 2배")
    shape(s, 5).text_frame.paragraphs[0].runs[0].font.size = bd.Pt(36)
    drop(s, *range(6, 28))
    bd.picture(s, bd.framed("opcurve_deck", DECK / "opcurve_deck.png"), 0.35, 1.7, 7.35)
    X = 7.95
    card(s, X - 0.1, 1.9, 5.0, 1.8, "0.85", "번", "100등판당 오경보 횟수\n다치지 않은 투수 · 설계값 1번\n실제 0.85번 · 2026 시즌 0.78번\n1마일 규칙은 6.7번", num_w=1.75, label_size=12, num_size=34)
    card(s, X - 0.1, 3.95, 5.0, 1.8, "2", "배", "경보 뒤 30일 안 팔 부상 IL\n경보 울렸을 때 10.5%\n안 울렸을 때 4.8%\n2026 시즌도 2.0배", num_w=1.75, label_size=12, num_size=34)
    bd.text(s, 0.6, 6.85, 12.2, 0.4, [[bd.body("2024~2025 시즌 결과 (2026 시즌은 봉인해 두었다가 10월 7일 한 번 계산) · MLB 투수-시즌 3,040개 · 팔 부상으로 IL에 오른 투수를 같은 시점의 건강한 투수 2명씩과 짝지어 비교", 11, bd.MUTED)]])


def s10(s):
    title(s, "피치시그널은 이렇게 쓰입니다")
    drop(s, *range(15, 35))
    rows = (("대회 운영본부", "운영본부와 각 팀이 같은 화면으로 규정 위반과 누적 부하 확인 · 전국체전·주말리그·전국대회, 대학·중학·리틀야구 대회에도"),
            ("협회 · 연맹", "기록지 사진만으로 공식 기록에 볼·스트라이크 추가 · 며칠 단위 누적 기준의 근거"),
            ("고교 · 아마추어 지도자", "오늘 누가 몇 구까지 · 팀 투수 누적 부하 관리 · 상대 투수 분석을 작전에"),
            ("고교 · 아마추어 선수", "경기 복기 · 제구 흐름과 약점 · 진학·드래프트용 시즌 기록"),
            ("스카우터 · 대학 감독", "고교 투수의 제구·사용량 이력 · 외국인 투수 영입 전 점검"),
            ("프로 구단 분석팀", "구단 추적 데이터로 구속·폼 경보 · 불펜 운영"))
    y = 1.7
    for name, desc in rows:
        bd.picture(s, DECK / "box_small.png", 0.55, y + 0.1, 2.35, 0.55)
        bd.text(s, 0.7, y + 0.15, 2.1, 0.45, [[bd.body(name, 13, bd.WHITE, True)]], anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER)
        bd.text(s, 3.1, y, 6.3, 0.76, [[bd.body(desc, 13, bd.INK)]], anchor=MSO_ANCHOR.MIDDLE, line=1.15)
        y += 0.86
    bd.picture(s, DECK / "qr.png", 10.55, 2.0, 1.7, 1.7)
    bd.text(s, 9.7, 3.85, 3.4, 0.9, [[bd.body("robinkim0221.github.io/pitch-signal", 11.5, bd.INK)], [bd.body("김형준 · UNIST · robin1967@unist.ac.kr", 11, bd.MUTED)]], align=PP_ALIGN.CENTER, line=1.3)
    bd.text(s, 9.7, 5.0, 3.4, 0.7, [[("감사합니다", bd.TITLE, 26, bd.INK)]], align=PP_ALIGN.CENTER)


def s13(s):
    """백업 달력을 본문과 같은 2026 전국체전으로 (2쪽 '7일 257구' 예시의 근거)."""
    title(s, "백업 · 2026 전국체전 등판 달력")
    drop(s, *[sh.shape_id for sh in s.shapes if sh.shape_type == 13 and sh.shape_id > 2])
    img = bd.framed("tour_2026", DECK / "tour_2026.png")
    w = 10.5; h = bd.fit(img, w)
    bd.picture(s, img, (bd.SW - w) / 2, 1.6 + max(0, (5.6 - h) / 2), w)


def main(src: str, out: str) -> None:
    prs = Presentation(src)
    sl = list(prs.slides)
    s1(sl[0]); s2(sl[1]); s3(sl[2]); s4(sl[3])
    video_caption(sl[4], "시연 1 · 고교 야구 — 2026 전국 고교 시즌 (영상)")
    s6(sl[5]); s7(sl[6])
    video_caption(sl[7], "시연 2 · MLB·KBO — 투수 시즌 화면과 팀 불펜 현황판 (영상)")
    s9(sl[8]); s10(sl[9]); s13(sl[12])
    for s in sl:
        for sh in s.shapes:                               # 한글을 단어 단위로 줄바꿈 (1차 수정과 같음)
            if sh.has_text_frame:
                for p in sh.text_frame.paragraphs:
                    p._p.get_or_add_pPr().set("eaLnBrk", "0")
                    for run in p.runs:
                        run._r.get_or_add_rPr().set("lang", "ko-KR")
    prs.save(out)
    print("저장:", out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
