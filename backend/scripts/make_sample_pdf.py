#!/usr/bin/env python3
"""
示例 PDF 生成工具

将示例 Markdown 产品手册渲染为 PDF，用于验证 PDF 解析链路
与 Day 24-25 评估脚本（验收要求：10 页以上 PDF 技术文档）。

使用 reportlab 内置 CID 字体（STSong-Light），无需系统安装中文字体。

用法:
    python scripts/make_sample_pdf.py [输出路径]
    默认: data/samples/oasis_curator_manual.pdf
"""

import re
import sys
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def clean_markdown_line(line: str) -> tuple[str, int]:
    """
    清理 Markdown 行，返回 (文本, 标题级别)。

    处理：标题 #、引用 >、加粗 **、无序列表 -。
    标题级别用于决定字号；0 表示正文。
    """
    level = 0
    m = re.match(r"^(#{1,4})\s+", line)
    if m:
        level = len(m.group(1))
        line = line[m.end() :]
    line = line.replace("**", "").replace("*", "")
    line = re.sub(r"^>\s?", "", line)
    line = re.sub(r"^[-•]\s+", "• ", line)
    line = re.sub(r"`([^`]*)`", r"\1", line)
    return line.strip(), level


def build_pdf(md_path: Path, out_path: Path) -> None:
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    styles = {
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

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title="Oasis Curator 产品手册",
    )

    story = []
    for raw in md_path.read_text(encoding="utf-8").splitlines():
        text, level = clean_markdown_line(raw)
        if not text:
            continue
        style = styles.get(level, styles[0])
        story.append(Paragraph(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), style))
        if level == 1:
            story.append(Spacer(1, 4))

    doc.build(story)
    print(f"PDF 已生成: {out_path}")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE_DIR / "oasis_curator_manual.pdf"
    build_pdf(SAMPLE_DIR / "oasis_curator_manual.md", out)


if __name__ == "__main__":
    main()
