"""발표자료 조립 (단계 12.1~12.3): docs/slides/slides.md를 16:9 PowerPoint로 만든다.

슬라이드는 '---' 줄로 나누고, 각 슬라이드는 아래 줄들로 적는다:
  # 제목            슬라이드 제목 (왼쪽 위)
  time: 0:35        배정 시간 (합계 확인용)
  layout: cover     표지 양식 (없으면 보통 양식)
  big: 35.6%        크게 보여 줄 숫자 하나 (60pt 이상)
  message: ...      화면에 크게 적는 핵심 메시지 한 문장 (값 안의 '\n' 두 글자는 줄바꿈)
  sub: ...          메시지 아래 작은 보조 문장
  - 항목            글머리표 (세 줄 이하)
  image: 경로       11.3 최종 그림 또는 화면 캡처 (저장소 기준 경로)
  source: ...       출처 (오른쪽 아래 10pt)
  notes: ...        발표 대본 (슬라이드 노트). 다음 필드나 '---'가 나올 때까지 여러 줄
  hidden: true      숨김 슬라이드 (시연 백업)
  qr: true          오른쪽 아래에 서비스 QR

디자인 규칙(12.2): 흰 배경, 제목 28pt 이상, 본문 18pt 이상, 글 세 줄 이하, 숫자 하나만 크게, 색은 대시보드와 같게.

사용 예:
    python tools/build_slides.py --out "C:/work/private/제출물/PitchSignal_발표.pptx"
"""
from __future__ import annotations

import argparse
import math
import re
import tempfile
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Cm, Pt

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "slides" / "slides.md"
FONT = "맑은 고딕"
INK, INK2, MUTED = RGBColor(0x11, 0x11, 0x11), RGBColor(0x4A, 0x4A, 0x48), RGBColor(0x8A, 0x88, 0x80)
ACCENT, OK, WARN, ALARM = RGBColor(0x1F, 0x3A, 0x6E), RGBColor(0x2E, 0x8B, 0x57), RGBColor(0xD9, 0x82, 0x2B), RGBColor(0xC8, 0x35, 0x2E)
W, H = Cm(33.867), Cm(19.05)                       # 16:9
SERVICE = "https://robinkim0221.github.io/pitch-signal/"
FIELDS = ("time", "layout", "big", "message", "sub", "image", "source", "hidden", "qr")


# ---------- 읽기 ----------

def parse_slides(text: str) -> list[dict]:
    slides = []
    for chunk in re.split(r"^---\s*$", text, flags=re.M):
        if not chunk.strip():
            continue
        s = {"title": "", "bullets": [], "notes": ""}
        notes: list[str] | None = None
        for line in chunk.splitlines():
            st = line.strip()
            m = re.match(r"^(\w+):\s?(.*)$", st)
            if st.startswith("# "):
                s["title"] = st[2:].strip(); notes = None
            elif st.startswith("- ") and notes is None:
                s["bullets"].append(st[2:].strip())
            elif m and m.group(1) == "notes":
                notes = [m.group(2)]
            elif m and m.group(1) in FIELDS:
                s[m.group(1)] = m.group(2).strip().replace("\\n", "\n"); notes = None      # 값 안의 '\n' 두 글자는 줄바꿈
            elif notes is not None and st:
                notes.append(st)
            if notes is not None:
                s["notes"] = "\n".join(x for x in notes if x is not None).strip()
        slides.append(s)
    return slides


def total_seconds(slides: list[dict]) -> int:
    total = 0
    for s in slides:
        if s.get("time"):
            m, sec = s["time"].split(":")
            total += int(m) * 60 + int(sec)
    return total


# ---------- 쓰기 ----------

def _text(slide, left, top, width, height, text, size, bold=False, color=INK, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame; tf.word_wrap = True; tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Cm(0.1)
    lines = text.split("\n") if isinstance(text, str) else list(text)
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        run = p.add_run(); run.text = line
        run.font.name = font; run.font.size = Pt(size); run.font.bold = bold; run.font.color.rgb = color
        p.space_after = Pt(6)
    return box


def _bullets(slide, left, top, width, height, items, size=20):
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame; tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        run = p.add_run(); run.text = "•  " + item
        run.font.name = FONT; run.font.size = Pt(size); run.font.color.rgb = INK2
        p.space_after = Pt(10)
    return box


def _picture(slide, path: Path, left, top, max_w, max_h):
    """상자 안에 비율을 지키며 그림을 넣는다."""
    from PIL import Image
    with Image.open(path) as im:
        w, h = im.size
    scale = min(max_w / w, max_h / h)
    pw, ph = int(w * scale), int(h * scale)
    return slide.shapes.add_picture(str(path), left + (max_w - pw) // 2, top + (max_h - ph) // 2, pw, ph)


def _qr(path: Path):
    import qrcode
    qrcode.make(SERVICE, box_size=8, border=2).save(path)


def _cover(slide, s: dict, qr: Path):
    _text(slide, Cm(2.5), Cm(5.2), Cm(24), Cm(3.2), s.get("message", ""), 40, bold=True, color=INK)
    _text(slide, Cm(2.5), Cm(8.6), Cm(24), Cm(2.4), s.get("sub", ""), 22, color=INK2)
    _text(slide, Cm(2.5), Cm(13.0), Cm(20), Cm(3.0), s.get("source", ""), 16, color=INK2)
    slide.shapes.add_picture(str(qr), Cm(27.0), Cm(12.3), Cm(4.6), Cm(4.6))
    _text(slide, Cm(26.3), Cm(17.0), Cm(6.2), Cm(1.0), SERVICE.replace("https://", ""), 10, color=MUTED, align=PP_ALIGN.CENTER)


def _height(text: str, size_pt: float, width_cm: float) -> float:
    """글 상자가 차지할 높이(cm) 어림. 한글 한 글자 폭을 글자 크기의 0.85배로 본다."""
    per_line = max(1, int(width_cm / (size_pt * 0.0353 * 0.85)))
    lines = sum(max(1, math.ceil(len(line) / per_line)) for line in text.splitlines())
    return lines * size_pt * 1.3 * 0.0353 + 0.35


def _normal(slide, s: dict, root: Path, number: int, total: int, qr: Path):
    _text(slide, Cm(1.6), Cm(0.9), Cm(30), Cm(1.8), s["title"], 28, bold=True, color=INK)
    line = slide.shapes.add_shape(1, Cm(1.7), Cm(2.75), Cm(2.2), Cm(0.12))        # 제목 아래 짧은 강조선
    line.fill.solid(); line.fill.fore_color.rgb = ACCENT; line.line.fill.background()
    has_image = bool(s.get("image"))
    width_cm = 14.5 if has_image else 30.5
    text_w = Cm(width_cm)
    y = 3.6
    if s.get("big"):
        size = 66 if len(s["big"]) <= 7 else 48
        h = _height(s["big"], size, width_cm)
        _text(slide, Cm(1.6), Cm(y), text_w, Cm(h), s["big"], size, bold=True, color=ACCENT); y += h
    if s.get("message"):
        size = 24 if (s.get("big") or has_image) else 28
        h = _height(s["message"], size, width_cm)
        _text(slide, Cm(1.6), Cm(y), text_w, Cm(h), s["message"], size, bold=True, color=INK); y += h
    if s.get("sub"):
        h = _height(s["sub"], 18, width_cm)
        _text(slide, Cm(1.6), Cm(y), text_w, Cm(h), s["sub"], 18, color=INK2); y += h
    if s["bullets"]:
        _bullets(slide, Cm(1.6), Cm(y), text_w, Cm(max(1.0, 17.0 - y)), s["bullets"][:3])
    if has_image:
        _picture(slide, root / s["image"], Cm(16.6), Cm(3.4), Cm(16.0), Cm(13.6))
    if s.get("qr", "").lower() == "true":
        left = Cm(1.6) if has_image else Cm(28.2)                                  # 그림이 있으면 글 아래 왼쪽에
        slide.shapes.add_picture(str(qr), left, Cm(12.6), Cm(4.2), Cm(4.2))
        _text(slide, left - Cm(1.6), Cm(16.8), Cm(7.4), Cm(0.9), SERVICE.replace("https://", ""), 11, color=INK2, align=PP_ALIGN.CENTER)
    if s.get("source"):
        _text(slide, Cm(14), Cm(17.9), Cm(18.3), Cm(0.9), s["source"], 10, color=MUTED, align=PP_ALIGN.RIGHT)
    _text(slide, Cm(1.6), Cm(17.9), Cm(6), Cm(0.9), f"{number} / {total}", 10, color=MUTED)


def build(md_path: Path, out: Path, root: Path = ROOT) -> Path:
    slides = parse_slides(Path(md_path).read_text(encoding="utf-8"))
    prs = Presentation(); prs.slide_width, prs.slide_height = W, H
    blank = prs.slide_layouts[6]
    shown = [s for s in slides if s.get("hidden", "").lower() != "true"]
    with tempfile.TemporaryDirectory() as tmp:
        qr = Path(tmp) / "qr.png"; _qr(qr)
        for s in slides:
            slide = prs.slides.add_slide(blank)
            if s.get("layout") == "cover":
                _cover(slide, s, qr)
            else:
                _normal(slide, s, root, shown.index(s) + 1 if s in shown else 0, len(shown), qr)
            if s.get("hidden", "").lower() == "true":
                slide._element.set("show", "0")
            slide.notes_slide.notes_text_frame.text = s.get("notes", "")
        out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
        prs.save(out)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(SOURCE))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    slides = parse_slides(Path(args.source).read_text(encoding="utf-8"))
    total = total_seconds(slides)
    out = build(Path(args.source), Path(args.out))
    print(f"저장: {out} (슬라이드 {len(slides)}장, 배정 시간 합계 {total // 60}:{total % 60:02d})")


if __name__ == "__main__":
    main()
