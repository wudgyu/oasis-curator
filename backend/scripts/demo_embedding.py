#!/usr/bin/env python3
"""
Embedding 演示工具

展示文本向量化与余弦相似度：语义相近的句子得分高，无关句子得分低。

用法:
    python scripts/demo_embedding.py                    # auto：有智谱 Key 用云端，否则本地 MiniLM
    python scripts/demo_embedding.py --provider zhipu   # 强制智谱 embedding-2（需 ZHIPU_API_KEY）
    python scripts/demo_embedding.py --provider minilm  # 强制本地 MiniLM（首次调用需下载约 80MB 模型）
"""

import argparse
import asyncio
import os
import sys

# 确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.embedder import cosine_similarity, get_embedder  # noqa: E402


class Colors:
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    END = "\033[0m"


# 演示语料：基准句 + 语义相近句 + 相关句 + 无关句
BASE_SENTENCE = "RAG 文档问答系统支持引用溯源"
PAIRS = [
    ("语义相近", "基于检索增强生成的问答平台，回答会标注信息来源"),
    ("语义相关", "知识库文档的向量化与语义检索"),
    ("语义无关", "今天晚餐吃什么好呢"),
    ("完全无关", "足球比赛的比分是多少"),
]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Embedding 相似度演示")
    parser.add_argument(
        "--provider",
        choices=["auto", "zhipu", "minilm"],
        default="auto",
        help="Embedding 模型选择（默认 auto）",
    )
    args = parser.parse_args()

    emb = get_embedder(args.provider)
    print(
        f"{Colors.BOLD}{Colors.CYAN}🧮 Embedding 模型: {emb.name}{Colors.END}"
        f"（维度 {emb.dimension}）"
    )
    if emb.name == "minilm":
        print(
            f"  {Colors.YELLOW}首次调用需下载本地模型（约 80MB），请稍候……{Colors.END}"
        )

    texts = [BASE_SENTENCE] + [t for _, t in PAIRS]
    print(f"{Colors.GRAY}向量化 {len(texts)} 条文本中……{Colors.END}")
    vectors = await emb.embed_texts(texts)

    print(f"\n{Colors.BOLD}{Colors.GREEN}📐 余弦相似度（基准句: {BASE_SENTENCE}）{Colors.END}\n")
    base = vectors[0]
    for (label, _), vec in zip(PAIRS, vectors[1:]):
        score = cosine_similarity(base, vec)
        bar = "█" * max(1, int(score * 20))
        print(f"  {label:<6} {score:+.4f}  {Colors.CYAN}{bar}{Colors.END}")

    print(f"\n{Colors.GRAY}基准句向量前 5 维: {[round(float(x), 4) for x in base[:5]]}{Colors.END}")
    if emb.name == "minilm":
        print(
            f"{Colors.YELLOW}注: MiniLM 为英文训练的轻量模型，中文语义区分能力有限；"
            f"配置 ZHIPU_API_KEY 后重跑 --provider zhipu 对比 embedding-2 的效果。{Colors.END}"
        )


if __name__ == "__main__":
    asyncio.run(main())
