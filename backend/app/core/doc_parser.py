"""
文档解析器

支持 PDF（pdfplumber）/ TXT / Markdown 三种格式，统一输出纯文本。

PDF 逐页提取并保留页码信息，供切分时标注 chunk 的来源页。
TXT/Markdown 按文本读取，UTF-8 优先、GBK 回退（中文文档常见编码）。
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}

# 统一换行符 + 折叠 3 个以上连续空行为单个空行（段落分隔）
_WHITESPACE_RE = re.compile(r"\n{3,}")


@dataclass
class ParsedDocument:
    """解析后的文档：纯文本 + 元信息"""

    text: str  # 全文纯文本（页间以空行分隔）
    file_name: str  # 原始文件名
    file_type: str  # pdf / txt / markdown
    char_count: int = 0  # 总字符数
    page_count: int = 0  # 页数（仅 PDF 有意义）
    pages: List[str] = field(default_factory=list)  # 每页文本（仅 PDF）


def parse_file(file_path: str | Path) -> ParsedDocument:
    """
    按扩展名分派解析。

    Raises:
        ValueError: 不支持的格式
        FileNotFoundError: 文件不存在
    """
    path = Path(file_path)
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"不支持的文档格式: {ext}（支持 {sorted(SUPPORTED_EXTENSIONS)}）")
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {path}")

    if ext == ".pdf":
        return _parse_pdf(path)
    file_type = "markdown" if ext in (".md", ".markdown") else "txt"
    return _parse_text_file(path, file_type)


def _parse_pdf(path: Path) -> ParsedDocument:
    """pdfplumber 逐页提取文本，页间以空行分隔，保留每页文本供页码标注"""
    import pdfplumber  # 延迟导入：非 PDF 场景不加载该依赖

    pages: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    text = "\n\n".join(pages)
    logger.info("PDF 解析完成: %s，共 %d 页，%d 字符", path.name, len(pages), len(text))
    return ParsedDocument(
        text=text,
        file_name=path.name,
        file_type="pdf",
        char_count=len(text),
        page_count=len(pages),
        pages=pages,
    )


def _parse_text_file(path: Path, file_type: str) -> ParsedDocument:
    """读取纯文本文件，UTF-8 优先，失败回退 GBK"""
    text = None
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = path.read_text(encoding=encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"无法识别文件编码（已尝试 utf-8/gbk）: {path.name}")
    return ParsedDocument(
        text=text,
        file_name=path.name,
        file_type=file_type,
        char_count=len(text),
    )
