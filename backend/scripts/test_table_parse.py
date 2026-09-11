#!/usr/bin/env python3
"""
多格式文档解析自测（离线，不依赖后端与模型服务）

覆盖：
- PDF 表格提取（pdfplumber）与 Word 表格提取（python-docx）
- 表格内容以 Markdown 形式进入正文，并能在切分后保留
- Word 标题层级（Heading → # 标记）保留

运行：python scripts/test_table_parse.py
（示例文档不存在时自动生成，依赖 reportlab / python-docx）
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(BACKEND_DIR / "scripts"))

from app.core.chunker import chunk_document  # noqa: E402
from app.core.doc_parser import parse_file, table_to_markdown  # noqa: E402

SAMPLE_DIR = BACKEND_DIR / "data" / "samples"
SRC_MD = SAMPLE_DIR / "oasis_curator_api_reference.md"
SAMPLE_PDF = SAMPLE_DIR / "oasis_curator_api_reference.pdf"
SAMPLE_DOCX = SAMPLE_DIR / "oasis_curator_api_reference.docx"

# 表格中的关键事实（问答时需要能检索到）
TABLE_FACTS = ["admin / manager", "enterprise", "bge-m3", "50 兆字节"]

passed = 0
failed = 0


def check(name: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}：期望 {expected}，实际 {actual}")


def ensure_samples() -> None:
    """示例文档缺失时自动生成"""
    if not SAMPLE_PDF.exists():
        from make_sample_pdf import build_pdf

        build_pdf(SRC_MD, SAMPLE_PDF)
    if not SAMPLE_DOCX.exists():
        from make_sample_docx import build_docx

        build_docx(SRC_MD, SAMPLE_DOCX)


def test_table_to_markdown() -> None:
    """表格转 Markdown 的边界处理"""
    print("\n[1] 表格转 Markdown")
    md = table_to_markdown([["列A", "列B"], ["1", "2"], [None, None]])
    check("表头与数据行渲染", md.splitlines()[0], "| 列A | 列B |")
    check("分隔行渲染", md.splitlines()[1], "| --- | --- |")
    check("整行空值被丢弃", len(md.splitlines()), 3)

    md_ragged = table_to_markdown([["A", "B", "C"], ["1", "2"]])
    check("列数不齐自动补齐", md_ragged.splitlines()[2], "| 1 | 2 |  |")

    check("空表格返回空串", table_to_markdown([]), "")


def test_pdf_tables() -> None:
    """PDF：表格提取 + 正文合并 + 切分保留"""
    print("\n[2] PDF 表格提取")
    doc = parse_file(SAMPLE_PDF)
    check("识别为 pdf", doc.file_type, "pdf")
    check("提取到 6 张表格", doc.table_count, 6)
    check("表格标记进入正文", "[表格 1]" in doc.text, True)
    for fact in TABLE_FACTS:
        check(f"表格事实可检索: {fact}", fact in doc.text, True)

    chunks = chunk_document(doc, strategy="paragraphs")
    table_chunks = [c for c in chunks if "| --- |" in c.text]
    check("含表格的 chunk 数 >= 4", len(table_chunks) >= 4, True)
    check("chunk 带页码", all(c.page for c in chunks), True)


def test_docx_tables() -> None:
    """Word：表格提取 + 标题层级 + 切分保留"""
    print("\n[3] Word 表格提取")
    doc = parse_file(SAMPLE_DOCX)
    check("识别为 word", doc.file_type, "word")
    check("提取到 6 张表格", doc.table_count, 6)
    for fact in TABLE_FACTS:
        check(f"表格事实可检索: {fact}", fact in doc.text, True)

    headings = [line for line in doc.text.splitlines() if line.startswith("#")]
    check("标题层级保留（1 个一级 + 7 个二级）", len(headings), 8)
    check("二级标题格式", headings[1].startswith("## "), True)

    chunks = chunk_document(doc, strategy="paragraphs")
    table_chunks = [c for c in chunks if "| --- |" in c.text]
    check("含表格的 chunk 数 >= 4", len(table_chunks) >= 4, True)


def main() -> None:
    ensure_samples()
    test_table_to_markdown()
    test_pdf_tables()
    test_docx_tables()
    print(f"\n{'=' * 50}\n通过 {passed} / {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
