#!/usr/bin/env python3
"""
文档切分演示工具

解析任意 PDF / TXT / Markdown 文档，对比展示两种切分策略的结果。

用法:
    python scripts/demo_chunk.py <文件路径>
    python scripts/demo_chunk.py <文件路径> --strategy both
    python scripts/demo_chunk.py <文件路径> --size 500 --overlap 100
    python scripts/demo_chunk.py <文件路径> --strategy paragraphs --min 500 --max 800
"""

import argparse
import os
import sys

# 确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.chunker import chunk_document  # noqa: E402
from app.core.doc_parser import parse_file  # noqa: E402


class Colors:
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_doc_info(doc) -> None:
    """打印文档元信息"""
    print(f"{Colors.BOLD}{Colors.CYAN}📄 文档解析结果{Colors.END}")
    print(f"  文件名: {doc.file_name}")
    print(f"  格式  : {doc.file_type}")
    print(f"  字符数: {doc.char_count}")
    if doc.page_count:
        print(f"  页数  : {doc.page_count}")


def print_chunks(chunks, title: str) -> None:
    """打印 chunk 列表及统计"""
    print(f"\n{Colors.BOLD}{Colors.GREEN}✂️  策略：{title}{Colors.END}")
    if not chunks:
        print(f"  {Colors.YELLOW}（无内容）{Colors.END}")
        return
    lengths = [len(c.text) for c in chunks]
    print(
        f"  {Colors.GRAY}chunk 数: {len(chunks)} | "
        f"平均长度: {sum(lengths) // len(lengths)} | "
        f"最短: {min(lengths)} | 最长: {max(lengths)}{Colors.END}"
    )
    for c in chunks:
        page = f" 第{c.page}页" if c.page else ""
        print(
            f"  {Colors.CYAN}[{c.chunk_index:>3}]{Colors.END}"
            f"{page} len={len(c.text):>4} | {c.preview(60)}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="文档切分演示工具")
    parser.add_argument("file", help="文档路径（PDF/TXT/Markdown）")
    parser.add_argument(
        "--strategy",
        choices=["both", "paragraphs", "chars"],
        default="both",
        help="展示哪种切分策略（默认 both）",
    )
    parser.add_argument("--size", type=int, default=500, help="固定字符数切分窗口大小")
    parser.add_argument("--overlap", type=int, default=100, help="固定字符数切分重叠")
    parser.add_argument("--min", dest="min_chars", type=int, default=500, help="段落策略目标最小长度")
    parser.add_argument("--max", dest="max_chars", type=int, default=800, help="段落策略最大长度")
    args = parser.parse_args()

    doc = parse_file(args.file)
    print_doc_info(doc)

    if args.strategy in ("both", "paragraphs"):
        print_chunks(
            chunk_document(
                doc,
                strategy="paragraphs",
                min_chars=args.min_chars,
                max_chars=args.max_chars,
            ),
            "paragraphs（按段落，合并至目标区间）",
        )
    if args.strategy in ("both", "chars"):
        print_chunks(
            chunk_document(
                doc,
                strategy="chars",
                chunk_size=args.size,
                overlap=args.overlap,
            ),
            f"chars（固定 {args.size} 字符，重叠 {args.overlap}）",
        )


if __name__ == "__main__":
    main()
