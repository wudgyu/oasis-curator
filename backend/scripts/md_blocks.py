#!/usr/bin/env python3
"""
Markdown 块解析辅助

把 Markdown 源拆成两类块，供示例文档生成脚本（PDF / Word）复用：
- ("para", (文本, 标题级别))  标题级别 0 表示正文
- ("table", 二维单元格列表)    首行作为表头，已剔除 | --- | 分隔行
"""

import re
from typing import List, Tuple

# 表格分隔行：| --- | :---: | 等
_SEPARATOR_CELL_RE = re.compile(r"^:?-{3,}:?$")


def parse_line(line: str) -> Tuple[str, int]:
    """清理单行 Markdown 标记，返回 (文本, 标题级别)"""
    line = line.rstrip()
    level = 0
    m = re.match(r"^(#{1,4})\s+", line)
    if m:
        level = len(m.group(1))
        line = line[m.end():]
    line = line.replace("**", "").replace("*", "")
    line = re.sub(r"^>\s?", "", line)
    line = re.sub(r"^[-•]\s+", "• ", line)
    line = re.sub(r"`([^`]*)`", r"\1", line)
    return line.strip(), level


def _split_table_row(line: str) -> List[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def parse_markdown_blocks(md_text: str) -> List[Tuple[str, object]]:
    """把 Markdown 文本拆为段落块与表格块（保持原顺序）"""
    blocks: List[Tuple[str, object]] = []
    lines = md_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        # 表格块：连续以 | 开头的行
        if line.lstrip().startswith("|"):
            rows: List[List[str]] = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                rows.append(_split_table_row(lines[i]))
                i += 1
            # 剔除分隔行
            rows = [
                r for r in rows
                if not all(_SEPARATOR_CELL_RE.match(c or "") for c in r)
            ]
            if rows:
                blocks.append(("table", rows))
            continue

        text, level = parse_line(line)
        if text:
            blocks.append(("para", (text, level)))
        i += 1
    return blocks
