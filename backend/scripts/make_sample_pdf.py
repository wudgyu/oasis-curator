#!/usr/bin/env python3
"""
示例 PDF 生成工具

将示例 Markdown 渲染为 PDF（含表格），用于验证 PDF 解析、表格提取
与 RAG 评估（验收要求：10 页以上 PDF 技术文档 / 含表格的 PDF）。

使用 reportlab 内置 CID 字体（STSong-Light），无需系统安装中文字体。

用法:
    python scripts/make_sample_pdf.py [输入.md] [输出.pdf]
    默认: data/samples/oasis_curator_manual.md -> oasis_curator_manual.pdf
"""

import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from md_blocks import parse_markdown_blocks  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"
PAGE_WIDTH = A4[0] - 5 * cm  # 左右各 2.5cm 页边距


def build_styles() -> dict:
    """正文与各级标题样式"""
    return {
        0: ParagraphStyle(
            "body", fontName="STSong-Light", fontSize=12, leading=21,
            spaceAfter=8, wordWrap="CJK",
        ),
        1: ParagraphStyle(
            "h1", fontName="STSong-Light", fontSize=18, leading=27,
            spaceBefore=14, spaceAfter=12, wordWrap="CJK",
        ),
        2: ParagraphStyle(
            "h2", fontName="STSong-Light", fontSize=15, leading=23,
            spaceBefore=10, spaceAfter=9, wordWrap="CJK",
        ),
        3: ParagraphStyle(
            "h3", fontName="STSong-Light", fontSize=13, leading=21,
            spaceBefore=8, spaceAfter=7, wordWrap="CJK",
        ),
    }


def escape(text: str) -> str:
    """Paragraph 使用类 XML 标记，需转义特殊字符"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_table(rows: list) -> Table:
    """二维数据转 reportlab 表格（单元格用 Paragraph 以支持中文换行）"""
    cell_style = ParagraphStyle(
        "cell", fontName="STSong-Light", fontSize=9, leading=13, wordWrap="CJK"
    )
    data = [[Paragraph(escape(c), cell_style) for c in row] for row in rows]
    col_width = PAGE_WIDTH / max(len(row) for row in rows)

    table = Table(data, colWidths=[col_width] * len(data[0]), hAlign="LEFT")
    table.setStyle(
        TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EFEFEF")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    return table


def build_pdf(md_path: Path, out_path: Path) -> None:
    """Markdown → PDF（段落 + 表格）"""
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    styles = build_styles()

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=md_path.stem,
    )

    story = []
    for kind, payload in parse_markdown_blocks(md_path.read_text(encoding="utf-8")):
        if kind == "table":
            story.append(Spacer(1, 4))
            story.append(build_table(payload))  # type: ignore[arg-type]
            story.append(Spacer(1, 8))
        else:
            text, level = payload  # type: ignore[misc]
            story.append(Paragraph(escape(text), styles.get(level, styles[0])))

    doc.build(story)
    print(f"PDF 已生成: {out_path}")


def main() -> None:
    args = sys.argv[1:]
    src = Path(args[0]) if args else SAMPLE_DIR / "oasis_curator_manual.md"
    out = Path(args[1]) if len(args) > 1 else src.with_suffix(".pdf")
    build_pdf(src, out)


if __name__ == "__main__":
    main()
