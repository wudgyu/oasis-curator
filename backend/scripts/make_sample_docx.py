#!/usr/bin/env python3
"""
示例 Word 生成工具

将示例 Markdown 渲染为 .docx（含表格），用于验证 Word 解析链路：
段落与标题层级、表格提取、以及表格内容的向量化检索。

用法:
    python scripts/make_sample_docx.py [输入.md] [输出.docx]
    默认: data/samples/oasis_curator_api_reference.md -> .docx
"""

import sys
from pathlib import Path

import docx
from docx.shared import Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))
from md_blocks import parse_markdown_blocks  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"


def build_docx(md_path: Path, out_path: Path) -> None:
    """Markdown → Word（标题用 Heading 样式以保留层级，表格用 Table Grid 样式）"""
    document = docx.Document()
    document.core_properties.title = md_path.stem

    # 中文字体：Word 默认 Calibri 显示中文会回退，显式设置宋体
    style = document.styles["Normal"]
    style.font.name = "SimSun"
    style.font.size = Pt(11)

    for kind, payload in parse_markdown_blocks(md_path.read_text(encoding="utf-8")):
        if kind == "table":
            rows = payload  # type: ignore[assignment]
            width = max(len(r) for r in rows)
            table = document.add_table(rows=len(rows), cols=width)
            table.style = "Table Grid"
            for i, row in enumerate(rows):
                for j in range(width):
                    table.cell(i, j).text = row[j] if j < len(row) else ""
        else:
            text, level = payload  # type: ignore[misc]
            if level:
                document.add_heading(text, level=min(level, 4))
            else:
                document.add_paragraph(text)

    document.save(str(out_path))
    print(f"Word 已生成: {out_path}")


def main() -> None:
    args = sys.argv[1:]
    src = Path(args[0]) if args else SAMPLE_DIR / "oasis_curator_api_reference.md"
    out = Path(args[1]) if len(args) > 1 else src.with_suffix(".docx")
    build_docx(src, out)


if __name__ == "__main__":
    main()
