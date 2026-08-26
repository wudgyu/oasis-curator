#!/usr/bin/env python3
"""
RAG 问答 CLI 工具

直接调用 rag_pipeline 完成检索 → 重排序 → 生成（流式输出），
终端内可视化展示重排序打分与引用标注。

用法:
    python scripts/rag_chat.py --tenant 星辰科技
    python scripts/rag_chat.py --tenant 星辰科技 --doc-id <文档ID>

特殊命令:
    /exit    退出
"""

import argparse
import asyncio
import os
import sys

# 确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.rag_pipeline import (  # noqa: E402
    MIN_RERANK_SCORE,
    REFUSE_ANSWER,
    RagPipeline,
)

# 管线静态工具（Prompt 拼接 / 引用解析），脚本内直接复用
_build_generation_prompt = RagPipeline._build_generation_prompt
_extract_citations = RagPipeline._extract_citations
from app.database import SessionLocal  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402


class Colors:
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    END = "\033[0m"


def resolve_tenant_id(name: str) -> str:
    """按租户名解析租户 ID"""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == name).first()
        if tenant is None:
            raise SystemExit(f"租户不存在: {name}（种子数据: 星辰科技/云端数据/智慧医疗）")
        return tenant.id
    finally:
        db.close()


async def ask_question(
    pipeline: RagPipeline, question: str, tenant_id: str, doc_id: str | None
) -> None:
    """完整 RAG 问答并打印过程"""
    # 1. 检索 + 重排序
    results = await pipeline.retrieve(question, tenant_id, doc_id=doc_id)
    reranked = await pipeline.rerank(question, results)
    print(f"\n{Colors.GRAY}向量检索 {len(results)} 条，重排序保留 {len(reranked)} 条:{Colors.END}")
    for i, c in enumerate(reranked, 1):
        print(
            f"  {Colors.CYAN}{i}. [{c.score}分] {c.chunk.source_file} 第{c.chunk.chunk_index + 1}段"
            f"{Colors.END} {Colors.GRAY}{c.reason}{Colors.END}"
        )

    # 2. 拒答判定
    if not reranked or max(c.score for c in reranked) < MIN_RERANK_SCORE:
        print(f"\n{Colors.YELLOW}{REFUSE_ANSWER}{Colors.END}")
        return

    # 3. 流式生成
    messages = [
        {
            "role": "system",
            "content": "你是 Oasis Curator 文档问答助手，只依据参考资料回答，实事求是。",
        },
        {"role": "user", "content": _build_generation_prompt(question, reranked)},
    ]
    print(f"\n{Colors.GREEN}{Colors.BOLD}回答:{Colors.END}")
    answer_parts: list[str] = []
    async for token in pipeline._llm.chat_stream(messages, temperature=0.3):
        print(token, end="", flush=True)
        answer_parts.append(token)
    answer = "".join(answer_parts)
    print()

    citations = _extract_citations(answer)
    if citations:
        print(f"{Colors.YELLOW}引用: {' | '.join(citations)}{Colors.END}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="RAG 问答 CLI")
    parser.add_argument("--tenant", required=True, help="租户名称（如 星辰科技）")
    parser.add_argument("--doc-id", default=None, help="可选：限定单文档检索")
    args = parser.parse_args()

    tenant_id = resolve_tenant_id(args.tenant)
    pipeline = RagPipeline()
    print(
        f"{Colors.BOLD}RAG 问答已就绪（租户: {args.tenant}，Embedding: {pipeline._embedder.name}）{Colors.END}"
    )
    print("输入问题开始，输入 /exit 退出")

    while True:
        try:
            question = input(f"\n{Colors.CYAN}提问> {Colors.END}").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question:
            continue
        if question == "/exit":
            break
        await ask_question(pipeline, question, tenant_id, args.doc_id)

    print("\n再见 👋")


if __name__ == "__main__":
    asyncio.run(main())
