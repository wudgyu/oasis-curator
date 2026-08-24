"""
文档切分器

两种策略（chunk 均记录来源文件名、段序号，PDF 段落策略额外记录页码）：
- chars       ：固定字符数滑动窗口 + 重叠（默认 500 / 100）
- paragraphs  ：按 \\n\\n 段落切分，短段落向后合并至 500-800 字符区间，
               超长段落按句边界再切（避免单个 chunk 过长）

参数建议（Day 24-25）：
    CHUNK_SIZE = 500        # 每个 chunk 500 字符
    CHUNK_OVERLAP = 100     # 相邻 chunk 重叠 100 字符
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from app.core.doc_parser import ParsedDocument

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
PARAGRAPH_MIN_CHARS = 500
PARAGRAPH_MAX_CHARS = 800

# 按句边界切分超长段落：句号/问号/感叹号/分号/换行之后
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？；!?;\n])")


@dataclass
class Chunk:
    """切分后的文本块"""

    text: str
    source_file: str  # 来源文件名
    chunk_index: int  # 段序号（从 0 开始，引用格式中展示为第 index+1 段）
    page: Optional[int] = None  # 来源页码（仅 PDF 段落策略），从 1 开始
    strategy: str = ""  # chars / paragraphs

    @property
    def citation(self) -> str:
        """引用标注：[来源: 文件名, 第N段]"""
        return f"[来源: {self.source_file}, 第{self.chunk_index + 1}段]"

    def preview(self, width: int = 60) -> str:
        """单行预览，用于调试输出"""
        flat = self.text.replace("\n", " ")
        return flat[:width] + ("..." if len(flat) > width else "")


# ---------------------------------------------------------------------------
# 文本预处理
# ---------------------------------------------------------------------------


def _normalize_whitespace(text: str) -> str:
    """统一换行符并折叠 3 个以上连续空行为单个空行（段落分隔）"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# 策略一：固定字符数 + 重叠
# ---------------------------------------------------------------------------


def chunk_by_chars(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> List[str]:
    """
    固定字符数滑动窗口切分，相邻窗口重叠 overlap 字符。

    重叠的意义：避免关键信息恰好被切在两个 chunk 的边界上，
    导致检索时上下文断裂（类似分页查询时的跨页数据问题）。
    """
    if chunk_size <= overlap:
        raise ValueError(f"chunk_size({chunk_size}) 必须大于 overlap({overlap})")
    text = _normalize_whitespace(text)
    if not text:
        return []

    step = chunk_size - overlap
    chunks: List[str] = []
    start = 0
    while start < len(text):
        piece = text[start : start + chunk_size].strip()
        if piece:
            chunks.append(piece)
        start += step
    return chunks


# ---------------------------------------------------------------------------
# 策略二：按段落
# ---------------------------------------------------------------------------


def _split_long_paragraph(para: str, max_chars: int) -> List[str]:
    """按句边界把超长段落拆成不超过 max_chars 的片段（仍超长则硬切兜底）"""
    sentences = [s for s in _SENTENCE_SPLIT_RE.split(para) if s.strip()]

    parts: List[str] = []
    current = ""
    for sentence in sentences:
        if current and len(current) + len(sentence) > max_chars:
            parts.append(current.strip())
            current = sentence
        else:
            current += sentence
    if current.strip():
        parts.append(current.strip())

    # 兜底：单句超长（如无标点的长文本）硬切
    result: List[str] = []
    for part in parts:
        while len(part) > max_chars:
            result.append(part[:max_chars].strip())
            part = part[max_chars:]
        if part:
            result.append(part)
    return result


def chunk_by_paragraphs(
    text: str,
    min_chars: int = PARAGRAPH_MIN_CHARS,
    max_chars: int = PARAGRAPH_MAX_CHARS,
) -> List[str]:
    """
    按 \\n\\n 段落切分，贪心合并短段落至目标区间 [min_chars, max_chars]：
    - 当前块达到 min_chars 即封口，保证 chunk 粒度适中
    - 单段超过 max_chars 时按句边界拆分
    """
    if max_chars <= min_chars:
        raise ValueError(f"max_chars({max_chars}) 必须大于 min_chars({min_chars})")
    text = _normalize_whitespace(text)
    if not text:
        return []

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current = ""
    for para in paragraphs:
        # 超长段落：先封口当前累积块，再单独拆分
        if len(para) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_split_long_paragraph(para, max_chars))
            continue
        # 合并会超过上限：封口，另起新块
        if current and len(current) + 2 + len(para) > max_chars:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
        # 达到目标粒度即封口
        if len(current) >= min_chars:
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


# ---------------------------------------------------------------------------
# 文档级切分入口
# ---------------------------------------------------------------------------


def chunk_document(
    doc: ParsedDocument,
    strategy: str = "paragraphs",
    **kwargs,
) -> List[Chunk]:
    """
    将解析后的文档切分为 chunk 列表，自动标注来源文件名、段序号、页码。

    Args:
        doc: parse_file 的返回结果
        strategy: "paragraphs"（默认）| "chars"
        **kwargs: 透传给对应策略（如 chunk_size / overlap / min_chars / max_chars）

    Note:
        PDF 的段落策略逐页切分以保留页码；跨页被截断的段落视为两段
        （pdfplumber 按页提取文本，无法可靠判断段落是否跨页延续）。
    """
    if strategy not in ("paragraphs", "chars"):
        raise ValueError(f"未知切分策略: {strategy}（支持 paragraphs / chars）")

    if strategy == "chars":
        texts = chunk_by_chars(
            doc.text,
            chunk_size=kwargs.get("chunk_size", CHUNK_SIZE),
            overlap=kwargs.get("overlap", CHUNK_OVERLAP),
        )
        return [
            Chunk(text=t, source_file=doc.file_name, chunk_index=i, strategy="chars")
            for i, t in enumerate(texts)
        ]

    # 段落策略：PDF 逐页切分保留页码，纯文本整体切分
    if doc.pages:
        chunks: List[Chunk] = []
        for page_no, page_text in enumerate(doc.pages, start=1):
            for t in chunk_by_paragraphs(
                page_text,
                min_chars=kwargs.get("min_chars", PARAGRAPH_MIN_CHARS),
                max_chars=kwargs.get("max_chars", PARAGRAPH_MAX_CHARS),
            ):
                chunks.append(
                    Chunk(
                        text=t,
                        source_file=doc.file_name,
                        chunk_index=len(chunks),
                        page=page_no,
                        strategy="paragraphs",
                    )
                )
        return chunks

    texts = chunk_by_paragraphs(
        doc.text,
        min_chars=kwargs.get("min_chars", PARAGRAPH_MIN_CHARS),
        max_chars=kwargs.get("max_chars", PARAGRAPH_MAX_CHARS),
    )
    return [
        Chunk(text=t, source_file=doc.file_name, chunk_index=i, strategy="paragraphs")
        for i, t in enumerate(texts)
    ]
