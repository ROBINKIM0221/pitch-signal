"""제안서 조립 (단계 11.1~11.4): docs/proposal/proposal.md를 Word 문서로 만든다.

표지(제목·이름·서비스 링크·QR), 쪽 번호, 제목 단계, 표, 그림과 캡션, 하이퍼링크를 넣는다. Markdown은 아래 부분집합만 쓴다:
#/##/### 제목, 문단, '- ' 글머리, '1. ' 번호, | 표 |, ![캡션](경로){width=15cm}, ``` 코드(수식) ```, '> ' 인용, <<<pagebreak>>>.
본문 안에서는 **굵게**, [글](주소), 그리고 http로 시작하는 주소를 링크로 바꾼다.

사용 예:
    python tools/build_proposal.py --out "C:/work/private/제출물/PitchSignal_김형준_제안서.docx" --pdf
"""
from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "proposal" / "proposal.md"
FONT = "맑은 고딕"
INK, INK2, MUTED, LINE = RGBColor(0x11, 0x11, 0x11), RGBColor(0x4A, 0x4A, 0x48), RGBColor(0x8A, 0x88, 0x80), "E4E3DC"
ACCENT = RGBColor(0x2A, 0x78, 0xD6)
COVER = {
    "title": "피치시그널 (PitchSignal)",
    "subtitle": "오경보율을 설계로 보장하는 투구 이상 신호 모니터링",
    "event": "2026 경기스포츠산업 공모전 · 제안서",
    "author": "김형준 · UNIST · robin1967@unist.ac.kr",
    "service": "https://robinkim0221.github.io/pitch-signal/",
    "repo": "https://github.com/ROBINKIM0221/pitch-signal",
    "date": "2026년 10월",
}


# ---------- Markdown 읽기 ----------

def parse_blocks(text: str) -> list[tuple]:
    """Markdown 부분집합을 블록 목록으로. 문단 안의 줄바꿈은 띄어쓰기로 잇는다."""
    blocks: list[tuple] = []
    lines = text.splitlines()
    i = 0
    para: list[str] = []

    def flush():
        if para:
            blocks.append(("p", " ".join(s.strip() for s in para)))
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            flush(); i += 1; continue
        if s == "<<<pagebreak>>>":
            flush(); blocks.append(("pagebreak",)); i += 1; continue
        m = re.match(r"^(#{1,3})\s+(.*)$", s)
        if m:
            flush(); blocks.append((f"h{len(m.group(1))}", m.group(2).strip())); i += 1; continue
        if s.startswith("```"):
            flush(); i += 1; code = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i].rstrip()); i += 1
            blocks.append(("code", "\n".join(code).strip("\n"))); i += 1; continue
        m = re.match(r"^!\[(.*?)\]\((.*?)\)(?:\{width=([\d.]+)cm\})?$", s)
        if m:
            flush(); blocks.append(("img", m.group(1), m.group(2), float(m.group(3)) if m.group(3) else 16.0)); i += 1; continue
        if s.startswith("|"):
            flush(); rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            blocks.append(("table", rows)); continue
        if s.startswith("> "):
            flush(); blocks.append(("quote", s[2:].strip())); i += 1; continue
        if re.match(r"^\[\d+\]\s", s):
            flush(); refs = []
            while i < len(lines) and re.match(r"^\[\d+\]\s", lines[i].strip()):
                refs.append(lines[i].strip()); i += 1
            blocks.append(("refs", refs)); continue
        if re.match(r"^- ", s) or re.match(r"^\d+\. ", s):
            flush(); kind = "ul" if s.startswith("- ") else "ol"; items = []
            while i < len(lines) and (re.match(r"^- ", lines[i].strip()) if kind == "ul" else re.match(r"^\d+\. ", lines[i].strip())):
                items.append(re.sub(r"^(- |\d+\. )", "", lines[i].strip())); i += 1
            blocks.append((kind, items)); continue
        para.append(line); i += 1
    flush()
    return blocks


INLINE = re.compile(r"(\*\*.+?\*\*|\[[^\]]+\]\([^)]+\)|https?://[^\s)\]]+)")


def inline_runs(text: str) -> list[tuple[str, bool, str | None]]:
    """본문 한 줄을 (글, 굵게, 링크 주소) 조각으로 나눈다."""
    runs = []
    for part in INLINE.split(text):
        if not part:
            continue
        link = re.fullmatch(r"\[([^\]]+)\]\(([^)]+)\)", part)
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            runs.append((part[2:-2], True, None))
        elif link:
            runs.append((link.group(1), False, link.group(2)))
        elif re.fullmatch(r"https?://\S+", part):
            runs.append((part, False, part))
        else:
            runs.append((part, False, None))
    return runs


# ---------- Word 쓰기 ----------

def _font(run, size=None, bold=None, color=None, italic=None, name=FONT):
    run.font.name = name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.font.bold = bold
    if italic is not None:
        run.font.italic = italic
    if color is not None:
        run.font.color.rgb = color


def _hyperlink(paragraph, url: str, text: str, size: float):
    part = paragraph.part
    r_id = part.relate_to(url, "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    link = OxmlElement("w:hyperlink"); link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r"); rpr = OxmlElement("w:rPr")
    fonts = OxmlElement("w:rFonts"); fonts.set(qn("w:ascii"), FONT); fonts.set(qn("w:hAnsi"), FONT); fonts.set(qn("w:eastAsia"), FONT)
    color = OxmlElement("w:color"); color.set(qn("w:val"), "2A78D6")
    u = OxmlElement("w:u"); u.set(qn("w:val"), "single")
    sz = OxmlElement("w:sz"); sz.set(qn("w:val"), str(int(size * 2)))
    for e in (fonts, color, u, sz):
        rpr.append(e)
    t = OxmlElement("w:t"); t.text = text; t.set(qn("xml:space"), "preserve")
    run.append(rpr); run.append(t); link.append(run)
    paragraph._p.append(link)


def _write_inline(paragraph, text: str, size: float, color=INK):
    for chunk, bold, url in inline_runs(text):
        if url:
            _hyperlink(paragraph, url, chunk, size)
        else:
            _font(paragraph.add_run(chunk), size=size, bold=bold or None, color=color)


def _shade(cell, hex_fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd"); shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), hex_fill)
    tc_pr.append(shd)


def _page_number(section):
    p = section.footer.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(); _font(run, size=9, color=MUTED)
    for tag, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if tag:
            fc = OxmlElement("w:fldChar"); fc.set(qn("w:fldCharType"), tag); run._r.append(fc)
        else:
            it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = text; run._r.append(it)


def _setup(doc: Document):
    section = doc.sections[0]
    section.orientation = WD_ORIENT.PORTRAIT
    section.page_width, section.page_height = Cm(21.0), Cm(29.7)
    section.left_margin = section.right_margin = Cm(2.0)
    section.top_margin, section.bottom_margin = Cm(2.0), Cm(1.8)
    normal = doc.styles["Normal"]
    normal.font.name = FONT; normal.font.size = Pt(10); normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.paragraph_format.space_after = Pt(5); normal.paragraph_format.line_spacing = 1.15
    for name, size, before in (("Heading 1", 15, 14), ("Heading 2", 12, 9), ("Heading 3", 10.5, 7)):
        st = doc.styles[name]
        st.font.name = FONT; st.font.size = Pt(size); st.font.bold = True; st.font.color.rgb = INK
        st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        st.paragraph_format.space_before = Pt(before); st.paragraph_format.space_after = Pt(4); st.paragraph_format.keep_with_next = True
    _page_number(section)


def _cover(doc: Document, qr_png: Path):
    def line(text, size, bold=False, color=INK, before=0, after=6, align=WD_ALIGN_PARAGRAPH.LEFT):
        p = doc.add_paragraph(); p.alignment = align
        p.paragraph_format.space_before = Pt(before); p.paragraph_format.space_after = Pt(after)
        _font(p.add_run(text), size=size, bold=bold, color=color)
        return p
    line(COVER["event"], 11, color=INK2, before=120, after=18)
    line(COVER["title"], 30, bold=True, after=4)
    line(COVER["subtitle"], 15, color=INK2, after=60)
    line(COVER["author"], 12, after=4)
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(2)
    _font(p.add_run("시제품: "), size=11, color=INK2); _hyperlink(p, COVER["service"], COVER["service"], 11)
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(14)
    _font(p.add_run("코드·평가 계획: "), size=11, color=INK2); _hyperlink(p, COVER["repo"], COVER["repo"], 11)
    doc.add_picture(str(qr_png), width=Cm(3.2))
    line("QR을 찍으면 시제품이 열립니다", 9, color=MUTED, after=40)
    line(COVER["date"], 11, color=INK2)
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def _qr(url: str, path: Path):
    import qrcode
    img = qrcode.make(url, box_size=8, border=2)
    img.save(path)


def _widths(rows: list[list[str]], ncol: int, total_cm: float = 17.0, min_cm: float = 1.7) -> list[float]:
    """열마다 가장 긴 칸의 글자 수에 비례해 폭을 나눈다 (너무 좁은 열은 최소 폭)."""
    longest = [max((len(r[c]) for r in rows if c < len(r)), default=1) for c in range(ncol)]
    weights = [min(max(w, 4), 40) ** 0.75 for w in longest]
    raw = [total_cm * w / sum(weights) for w in weights]
    fixed = [max(w, min_cm) for w in raw]
    scale = total_cm / sum(fixed)
    return [w * scale for w in fixed]


def _table(doc: Document, rows: list[list[str]]):
    ncol = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncol)
    table.style = "Table Grid"; table.alignment = WD_TABLE_ALIGNMENT.CENTER; table.autofit = False
    widths = _widths(rows, ncol)
    for ri, row in enumerate(rows):
        tr_pr = table.rows[ri]._tr.get_or_add_trPr(); tr_pr.append(OxmlElement("w:cantSplit"))
        if ri == 0:
            tr_pr.append(OxmlElement("w:tblHeader"))                      # 쪽이 바뀌면 머리글 행을 다시 보여 준다
        for ci in range(ncol):
            cell = table.cell(ri, ci); text = row[ci] if ci < len(row) else ""
            cell.width = Cm(widths[ci])
            p = cell.paragraphs[0]; p.paragraph_format.space_after = Pt(0); p.paragraph_format.line_spacing = 1.05
            if ri == 0:
                _shade(cell, "F1F0EA")
                _font(p.add_run(text), size=8.5, bold=True, color=INK)
            else:
                _write_inline(p, text, 8.5)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)


def _image(doc: Document, caption: str, path: Path, width_cm: float):
    doc.add_picture(str(path), width=Cm(width_cm))
    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.paragraphs[-1].paragraph_format.keep_with_next = True
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    p.paragraph_format.left_indent = p.paragraph_format.right_indent = Cm(0.6); p.paragraph_format.space_after = Pt(8)
    _write_inline(p, caption, 8.5, color=INK2)


def build(md_path: Path, out: Path, root: Path = ROOT) -> Path:
    """Markdown 원고를 읽어 Word 문서를 쓴다. 그림 경로는 root 기준이다."""
    doc = Document()
    _setup(doc)
    with tempfile.TemporaryDirectory() as tmp:
        qr = Path(tmp) / "qr.png"; _qr(COVER["service"], qr)
        _cover(doc, qr)
        for block in parse_blocks(Path(md_path).read_text(encoding="utf-8")):
            kind = block[0]
            if kind in ("h1", "h2", "h3"):
                doc.add_heading(block[1], level=int(kind[1]))
            elif kind == "p":
                _write_inline(doc.add_paragraph(), block[1], 10)
            elif kind == "ul":
                for item in block[1]:
                    p = doc.add_paragraph(style="List Bullet"); p.paragraph_format.space_after = Pt(2)
                    _write_inline(p, item, 10)
            elif kind == "ol":
                for n, item in enumerate(block[1], 1):
                    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(2)
                    p.paragraph_format.left_indent = Cm(0.75); p.paragraph_format.first_line_indent = Cm(-0.55)
                    _write_inline(p, f"{n}.  {item}", 10)
            elif kind == "refs":
                for ref in block[1]:
                    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(1.5); p.paragraph_format.line_spacing = 1.05
                    p.paragraph_format.left_indent = Cm(0.9); p.paragraph_format.first_line_indent = Cm(-0.9)
                    _write_inline(p, ref, 8.5, color=INK2)
            elif kind == "table":
                _table(doc, block[1])
            elif kind == "img":
                _image(doc, block[1], root / block[2], block[3])
            elif kind == "code":
                p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                p.paragraph_format.space_before = Pt(4); p.paragraph_format.space_after = Pt(8)
                _font(p.add_run(block[1]), size=10, name="Cambria Math", color=INK)
            elif kind == "quote":
                p = doc.add_paragraph(); p.paragraph_format.left_indent = Cm(0.8); p.paragraph_format.right_indent = Cm(0.8)
                _write_inline(p, block[1], 10.5, color=ACCENT)
                for run in p.runs:
                    run.font.bold = True
            elif kind == "pagebreak":
                doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        out = Path(out); out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(out)
    return out


def to_pdf(docx_path: Path, pdf_path: Path) -> Path:
    """설치된 Word로 PDF를 만든다 (다른 이름으로 저장 → PDF와 같음)."""
    script = (f"$w = New-Object -ComObject Word.Application; $w.Visible = $false; "
              f"$d = $w.Documents.Open('{Path(docx_path).resolve()}'); $d.ExportAsFixedFormat('{Path(pdf_path).resolve()}', 17); "
              f"$d.Close(0); $w.Quit()")
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)
    return pdf_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(SOURCE))
    ap.add_argument("--out", required=True, help="만들 .docx 경로")
    ap.add_argument("--pdf", action="store_true", help="같은 이름의 PDF도 만든다 (Word 필요)")
    args = ap.parse_args()
    out = build(Path(args.source), Path(args.out))
    print(f"저장: {out}")
    if args.pdf:
        pdf = to_pdf(out, out.with_suffix(".pdf"))
        print(f"저장: {pdf}")


if __name__ == "__main__":
    main()
