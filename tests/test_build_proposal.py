"""제안서 조립 도구 테스트 (단계 11.1~11.4). 실행: python -m pytest -q tests/test_build_proposal.py"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_proposal", ROOT / "tools" / "build_proposal.py")
bp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bp)

SAMPLE = """# 1. 문제

첫 문단 **굵게** 그리고 [링크](https://example.com) 끝.
이어지는 줄.

- 항목 하나
- 항목 둘

| 열 A | 열 B |
|---|---|
| 1 | 2 |

![그림 1. 캡션](reports/figures/final/01_system.png){width=12cm}

```
u = x / 2
```

> 인용 문단

<<<pagebreak>>>

## 1.1 소제목
"""


def test_parse_blocks_recognises_every_block_kind_in_order():
    kinds = [b[0] for b in bp.parse_blocks(SAMPLE)]
    assert kinds == ["h1", "p", "ul", "table", "img", "code", "quote", "pagebreak", "h2"]


def test_parse_blocks_joins_wrapped_lines_and_reads_table_rows_and_image_fields():
    blocks = {b[0]: b for b in bp.parse_blocks(SAMPLE)}
    assert blocks["p"][1] == "첫 문단 **굵게** 그리고 [링크](https://example.com) 끝. 이어지는 줄."
    assert blocks["ul"][1] == ["항목 하나", "항목 둘"]
    assert blocks["table"][1] == [["열 A", "열 B"], ["1", "2"]]              # 구분선(---)은 행이 아니다
    assert blocks["img"][1:] == ("그림 1. 캡션", "reports/figures/final/01_system.png", 12.0)
    assert blocks["code"][1] == "u = x / 2" and blocks["quote"][1] == "인용 문단"


def test_inline_runs_split_bold_links_and_bare_urls():
    runs = bp.inline_runs("A **B** [C](https://c.io) https://d.io 끝")
    assert runs == [("A ", False, None), ("B", True, None), (" ", False, None), ("C", False, "https://c.io"),
                    (" ", False, None), ("https://d.io", False, "https://d.io"), (" 끝", False, None)]


def test_build_writes_a_docx_with_cover_headings_and_pictures(tmp_path):
    md = tmp_path / "p.md"
    md.write_text(SAMPLE, encoding="utf-8")
    out = tmp_path / "p.docx"
    bp.build(md, out, root=ROOT)
    from docx import Document
    doc = Document(out)
    texts = [p.text for p in doc.paragraphs]
    assert any("피치시그널" in t for t in texts) and any("robin1967@unist.ac.kr" in t for t in texts)     # 표지
    assert "1. 문제" in texts and "1.1 소제목" in texts
    assert len(doc.inline_shapes) == 2                                                             # QR + 그림 1
    assert len(doc.tables) == 1 and doc.tables[0].cell(1, 1).text == "2"


def test_inline_runs_leave_bracketed_plain_text_alone():
    assert bp.inline_runs("[1] 출처 [실행 뒤 기입]") == [("[1] 출처 [실행 뒤 기입]", False, None)]


def test_parse_blocks_keeps_each_reference_entry_separate():
    blocks = bp.parse_blocks("## 8.2 참고문헌\n\n[1] 첫 출처. https://a.io\n[2] 둘째 출처.\n")
    assert blocks[1] == ("refs", ["[1] 첫 출처. https://a.io", "[2] 둘째 출처."])
