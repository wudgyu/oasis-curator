#!/usr/bin/env python3
"""
RAG 评估脚本

将示例产品手册（11 页 PDF）导入评估专用租户，用 5 个标准问题
自动跑完整 RAG 管线，输出每个问题的召回率与答案质量评分，
并验证文档外问题的拒答表现。

评分口径：
- 召回率: 重排序后的 Top-3 是否包含答案所在的文本块（按关键短语定位）
- 答案质量: 回答中包含的期望关键词比例
- 引用正确性: 回答中标注的引用是否都来自重排序保留的候选块

用法:
    python scripts/eval_rag.py
"""

import asyncio
import os
import sys
from pathlib import Path

# 确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.chunker import chunk_document  # noqa: E402
from app.core.doc_parser import parse_file  # noqa: E402
from app.core.embedder import embedder  # noqa: E402
from app.core.rag_pipeline import RagPipeline  # noqa: E402
from app.core.vector_store import vector_store  # noqa: E402

SAMPLE_PDF = os.path.join(
    os.path.dirname(__file__), "..", "data", "samples", "oasis_curator_manual.pdf"
)
SAMPLE_MD = os.path.join(
    os.path.dirname(__file__), "..", "data", "samples", "oasis_curator_manual.md"
)


def ensure_sample_pdf() -> None:
    """PDF 不存在时用 make_sample_pdf 自动生成（PDF 不入库，可再生成）"""
    if os.path.exists(SAMPLE_PDF):
        return
    from scripts.make_sample_pdf import build_pdf

    print("示例 PDF 不存在，自动生成……")
    build_pdf(Path(SAMPLE_MD), Path(SAMPLE_PDF))
EVAL_DOC_ID = "eval-oasis-manual"
EVAL_TENANT_ID = "eval-tenant"

# 标准问题：
# - answer_evidence: 答案所在 chunk 的关键短语（可多条，命中任一条即视为召回到答案块）
# - keywords: 回答中必须包含的核心事实词（等价表述只取一条）
QUESTIONS = [
    {
        "question": "RAG 问答的重排序保留几个候选块？",
        "answer_evidence": ["取分数最高的 3 个", "重排序后取 Top-3"],
        "keywords": ["Top-3"],
    },
    {
        "question": "固定字符数切分策略的窗口大小和重叠分别是多少？",
        "answer_evidence": ["相邻窗口重叠 100 字符", "固定字符数切分默认 500 字符"],
        "keywords": ["500"],
    },
    {
        "question": "离线模式使用什么模型做向量化？",
        "answer_evidence": ["BGE-large-zh-v1.5 做向量化", "Embedding 使用本地 BGE-large-zh-v1.5"],
        "keywords": ["BGE-large-zh-v1.5"],
    },
    {
        "question": "MCP 文档服务注册了哪三个工具？",
        "answer_evidence": ["list_documents 列出当前租户可访问的文档清单"],
        "keywords": ["search_documents"],
    },
    {
        "question": "质量保障 Agent 验证不通过时最多重新生成几轮？",
        "answer_evidence": ["最多循环三轮"],
        "keywords": ["三轮"],
    },
]

# 文档外问题：期望拒答
OUT_OF_SCOPE = "平台支持哪些数据库的 SQL 方言？"


class Colors:
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    END = "\033[0m"


async def ingest_sample() -> int:
    """解析示例 PDF → 切分 → 向量化 → 写入评估租户（幂等：先清理旧数据）"""
    parsed = await asyncio.to_thread(parse_file, SAMPLE_PDF)
    chunks = await asyncio.to_thread(chunk_document, parsed, strategy="paragraphs")
    embeddings = await embedder.embed_texts([c.text for c in chunks])
    await asyncio.to_thread(
        vector_store.delete_document, EVAL_DOC_ID, EVAL_TENANT_ID
    )
    await asyncio.to_thread(
        vector_store.add_chunks, chunks, embeddings, EVAL_DOC_ID, EVAL_TENANT_ID
    )
    return len(chunks)


async def run_eval(pipeline: RagPipeline) -> None:
    ensure_sample_pdf()
    chunk_count = await ingest_sample()
    print(
        f"{Colors.BOLD}📚 评估文档已入库: {EVAL_DOC_ID}"
        f"（{chunk_count} chunks, Embedding: {pipeline._embedder.name}）{Colors.END}\n"
    )

    recall_hits = 0
    keyword_hits_total = 0
    keyword_total = 0
    citation_valid = 0

    print(f"{Colors.BOLD}{'问题':<34} 召回  关键词  引用  拒答{Colors.END}")
    print(f"{Colors.GRAY}{'-' * 70}{Colors.END}")

    for i, item in enumerate(QUESTIONS):
        question = item["question"]
        result = await pipeline.answer(question, EVAL_TENANT_ID)

        # 召回：重排序后的候选块是否包含答案所在 chunk 的关键短语（任一条命中即可）
        hit = any(
            ev in c.chunk.text
            for c in result.reranked
            for ev in item["answer_evidence"]
        )
        recall_hits += int(hit)

        # 答案质量：期望关键词命中比例
        hits = sum(1 for kw in item["keywords"] if kw in result.answer)
        keyword_hits_total += hits
        keyword_total += len(item["keywords"])

        # 引用正确性：回答中引用的 chunk 都来自重排序结果（统一为 文件名, 第N段 格式比较）
        valid_citations = {
            f"{c.chunk.source_file}, 第{c.chunk.chunk_index + 1}段"
            for c in result.reranked
        }
        parsed_citations = set(result.citations)
        ok_citation = parsed_citations <= valid_citations and bool(parsed_citations)
        citation_valid += int(ok_citation)

        recall_mark = f"{Colors.GREEN}✓{Colors.END}" if hit else f"{Colors.RED}✗{Colors.END}"
        kw_mark = f"{hits}/{len(item['keywords'])}"
        cit_mark = f"{Colors.GREEN}✓{Colors.END}" if ok_citation else f"{Colors.RED}✗{Colors.END}"
        refused = f"{Colors.YELLOW}拒答{Colors.END}" if result.refused else ""
        print(f"  {question:<30}  {recall_mark}    {kw_mark}    {cit_mark}    {refused}")
        print(f"  {Colors.GRAY}答: {result.answer[:80]}{'...' if len(result.answer) > 80 else ''}{Colors.END}")

    # 文档外问题
    out_result = await pipeline.answer(OUT_OF_SCOPE, EVAL_TENANT_ID)
    refused_ok = out_result.refused or "没有相关信息" in out_result.answer
    refused_mark = f"{Colors.GREEN}✓{Colors.END}" if refused_ok else f"{Colors.RED}✗{Colors.END}"
    print(f"  {OUT_OF_SCOPE:<30}  {'—':<4} {'—':<5} {'—':<5} {refused_mark}")
    print(f"  {Colors.GRAY}答: {out_result.answer[:80]}{Colors.END}")

    # 汇总
    total = len(QUESTIONS)
    print(f"\n{Colors.BOLD}📊 评估汇总{Colors.END}")
    print(f"  召回率（Top-3 命中答案块）: {recall_hits}/{total} = {recall_hits / total * 100:.0f}%")
    print(f"  答案质量（关键词命中）    : {keyword_hits_total}/{keyword_total} = {keyword_hits_total / keyword_total * 100:.0f}%")
    print(f"  引用正确率                : {citation_valid}/{total} = {citation_valid / total * 100:.0f}%")
    print(f"  拒答表现                  : {'正确' if refused_ok else '错误（未拒答）'}")

    # 清理评估数据
    await asyncio.to_thread(vector_store.delete_document, EVAL_DOC_ID, EVAL_TENANT_ID)
    print(f"{Colors.GRAY}评估数据已清理{Colors.END}")


if __name__ == "__main__":
    asyncio.run(run_eval(RagPipeline()))
