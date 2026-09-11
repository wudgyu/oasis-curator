"""
RAG 问答管线（手写实现，不依赖 LangChain 等框架）

流程：
    问题向量化 → 向量检索 Top-5（租户过滤） → LLM 重排序打分取 Top-3
    → Prompt 拼接（含拒答约束） → LLM 生成（带 [来源: 文件名, 第N段] 引用）

参数（Day 24-25 建议）：
    TOP_K_RETRIEVAL = 5     # 向量检索返回 Top-5
    TOP_K_RERANK = 3        # 重排序后保留 Top-3
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import AsyncGenerator, Callable, List, Optional

from app.core.config import settings
from app.core.embedder import embedder
from app.core.llm_provider import LLMProvider, llm_provider
from app.core.vector_store import SearchResult, vector_store

logger = logging.getLogger(__name__)

TOP_K_RETRIEVAL = 5
TOP_K_RERANK = 3

# 重排序最低分阈值：最高分低于该值视为"文档中无答案"，直接拒答（省一次生成调用）
MIN_RERANK_SCORE = 4

# 引用标注解析：[来源: 文件名, 第N段]
CITATION_RE = re.compile(r"\[来源[:：]\s*([^,\]\[]+),\s*第(\d+)段\]")

# 拒答话术
REFUSE_ANSWER = "抱歉，当前文档库中没有相关信息。"


@dataclass
class RerankedChunk:
    """重排序后的候选块"""

    chunk: SearchResult
    score: int  # LLM 打分 1-10
    reason: str = ""


@dataclass
class RagAnswer:
    """RAG 问答结果"""

    answer: str
    citations: List[str] = field(default_factory=list)  # ["文件名, 第N段"]
    refused: bool = False  # 是否判定"文档中无答案"
    retrieved_count: int = 0
    reranked: List[RerankedChunk] = field(default_factory=list)
    provider: str = ""
    model: str = ""


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 输出中提取 JSON 对象（容忍代码块包裹与前后缀文本）"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class RagPipeline:
    """
    检索增强生成管线

    检索、重排序、拒答判定、生成四步串联；重排序与生成由 LLM 完成，
    检索与向量存储为手写实现。
    """

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        store=None,
        emb=None,
    ) -> None:
        self._llm = llm or llm_provider
        self._store = store or vector_store
        self._embedder = emb or embedder

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        question: str,
        tenant_id: str,
        top_k: int = TOP_K_RETRIEVAL,
        doc_id: Optional[str] = None,
        visibility_filter: Optional[Callable[[dict], bool]] = None,
    ) -> List[SearchResult]:
        """问题向量化 → 向量检索 Top-K（强制租户过滤 + 可见性过滤）"""
        query_embedding = (await self._embedder.embed_texts([question]))[0]
        results = await asyncio.to_thread(
            self._store.search,
            query_embedding,
            tenant_id,
            top_k,
            doc_id,
            visibility_filter,
        )
        logger.info("检索完成: %d 条命中", len(results))
        return results

    # ------------------------------------------------------------------
    # 重排序（LLM 打分）
    # ------------------------------------------------------------------

    async def rerank(
        self,
        question: str,
        results: List[SearchResult],
        top_n: int = TOP_K_RERANK,
    ) -> List[RerankedChunk]:
        """
        LLM 对每个候选块打分（1-10），取分数最高的 top_n 个。

        打分输出为 JSON；解析失败时重试一次，仍失败则退化为向量序取前 top_n
        （保证管线不因格式问题中断）。
        """
        if not results:
            return []

        messages = [
            {
                "role": "system",
                "content": (
                    "你是检索结果相关性评估器。给定用户问题与候选文本块，"
                    "为每个块打分（1-10 分）：10 分=完全直接回答问题；"
                    "5 分=部分相关；1 分=完全不相关。只输出 JSON，"
                    '格式：{"scores": [{"index": 0, "score": 8, "reason": "一句话理由"}]}'
                ),
            },
            {
                "role": "user",
                "content": "问题：{question}\n\n候选块：\n{candidates}".format(
                    question=question,
                    candidates="\n\n".join(
                        f"[{i}] {r.text}" for i, r in enumerate(results)
                    ),
                ),
            },
        ]

        try:
            response = await self._llm.chat(messages, temperature=0, max_tokens=600)
        except Exception as e:
            logger.warning("重排序 LLM 调用失败，退化向量序: %s", e)
            return [
                RerankedChunk(chunk=r, score=0, reason="重排序失败，按向量序保留")
                for r in results[:top_n]
            ]

        parsed = _extract_json(response.content)
        if parsed is None:
            logger.warning("重排序输出解析失败，退化向量序")
            return [
                RerankedChunk(chunk=r, score=0, reason="解析失败，按向量序保留")
                for r in results[:top_n]
            ]

        scored: List[RerankedChunk] = []
        for item in parsed.get("scores", []):
            index = item.get("index")
            if not isinstance(index, int) or not (0 <= index < len(results)):
                continue
            scored.append(
                RerankedChunk(
                    chunk=results[index],
                    score=int(item.get("score", 0)),
                    reason=str(item.get("reason", "")),
                )
            )
        if not scored:
            return results[:top_n]
        scored.sort(key=lambda c: c.score, reverse=True)
        return scored[:top_n]

    # ------------------------------------------------------------------
    # 生成
    # ------------------------------------------------------------------

    @staticmethod
    def _build_generation_prompt(
        question: str, reranked: List[RerankedChunk]
    ) -> str:
        """拼接生成提示词（含拒答约束与引用格式要求）"""
        references = "\n\n".join(
            f"[{i + 1}]（来源: {c.chunk.source_file}，第{c.chunk.chunk_index + 1}段）\n{c.chunk.text}"
            for i, c in enumerate(reranked)
        )
        return (
            "根据以下参考资料回答问题。如果资料中没有答案，"
            f'请明确回答"{REFUSE_ANSWER}"，不要编造。\n\n'
            f"参考资料：\n{references}\n\n"
            f"问题：{question}\n\n"
            "回答要求：\n"
            "1. 只依据参考资料回答，不要使用你自己的知识\n"
            "2. 每个关键事实后标注引用，格式 [来源: 文件名, 第N段]\n"
            "3. 回答简洁准确"
        )

    async def _generate(
        self, question: str, reranked: List[RerankedChunk]
    ) -> RagAnswer:
        messages = [
            {
                "role": "system",
                "content": "你是 Oasis Curator 文档问答助手，只依据参考资料回答，实事求是。",
            },
            {"role": "user", "content": self._build_generation_prompt(question, reranked)},
        ]
        response = await self._llm.chat(messages, temperature=0.3)
        return RagAnswer(
            answer=response.content or "",
            provider=response.provider,
            model=response.model,
        )

    @staticmethod
    def _extract_citations(answer: str) -> List[str]:
        """从回答中提取引用标注，按出现顺序去重"""
        seen, citations = set(), []
        for file_name, index in CITATION_RE.findall(answer):
            citation = f"{file_name.strip()}, 第{index}段"
            if citation not in seen:
                seen.add(citation)
                citations.append(citation)
        return citations

    # ------------------------------------------------------------------
    # 完整链路
    # ------------------------------------------------------------------

    async def answer(
        self,
        question: str,
        tenant_id: str,
        top_k: int = TOP_K_RETRIEVAL,
        top_n: int = TOP_K_RERANK,
        doc_id: Optional[str] = None,
        visibility_filter: Optional[Callable[[dict], bool]] = None,
    ) -> RagAnswer:
        """
        完整 RAG 问答：检索 → 重排序 → 生成（含拒答判定）。

        Args:
            question: 用户问题
            tenant_id: 租户过滤（必传）
            top_k: 向量检索返回条数
            top_n: 重排序保留条数
            doc_id: 可选，限定单文档检索
            visibility_filter: 可选，文档可见性谓词（不传则不做文档级权限过滤）
        """
        results = await self.retrieve(question, tenant_id, top_k, doc_id, visibility_filter)
        reranked = await self.rerank(question, results, top_n)

        base = RagAnswer(
            answer="",
            retrieved_count=len(results),
            reranked=reranked,
        )

        # 拒答判定：无检索结果，或重排序最高分低于阈值
        if not reranked or max(c.score for c in reranked) < MIN_RERANK_SCORE:
            logger.info(
                "拒答: 检索 %d 条，重排序最高分 %s < %d",
                len(results),
                max((c.score for c in reranked), default=0),
                MIN_RERANK_SCORE,
            )
            base.answer = REFUSE_ANSWER
            base.refused = True
            return base

        answer = await self._generate(question, reranked)
        answer.retrieved_count = base.retrieved_count
        answer.reranked = base.reranked

        # 后处理：门控放行但 LLM 判定无答案（回答含拒答话术）→ 标记拒答并清理引用
        if REFUSE_ANSWER in answer.answer:
            answer.refused = True
            answer.citations = []
            return answer

        answer.citations = self._extract_citations(answer.answer)
        return answer

    # ------------------------------------------------------------------
    # 流式链路（供 SSE 接口使用）
    # ------------------------------------------------------------------

    async def answer_stream(
        self,
        question: str,
        tenant_id: str,
        top_k: int = TOP_K_RETRIEVAL,
        top_n: int = TOP_K_RERANK,
        doc_id: Optional[str] = None,
        visibility_filter: Optional[Callable[[dict], bool]] = None,
    ) -> AsyncGenerator[dict, None]:
        """
        流式 RAG 问答，产出事件字典：

            {"type": "meta",  "retrieved_count": int, "reranked": [...]}
            {"type": "token", "text": str}
            {"type": "done",  "answer": str, "refused": bool, "citations": [...],
                              "provider": str, "model": str}

        检索与重排序必须完成后才能开始生成（需要上下文），
        因此 meta 事件先于 token 事件发出，供前端即时展示引用来源。
        """
        results = await self.retrieve(question, tenant_id, top_k, doc_id, visibility_filter)
        reranked = await self.rerank(question, results, top_n)

        yield {
            "type": "meta",
            "retrieved_count": len(results),
            "reranked": [
                {
                    "score": c.score,
                    "reason": c.reason,
                    "text": c.chunk.text[:200],
                    "source_file": c.chunk.source_file,
                    "chunk_index": c.chunk.chunk_index,
                    "page": c.chunk.page,
                }
                for c in reranked
            ],
        }

        # 拒答判定：无候选或最高分低于阈值 → 不调用 LLM，直接给出拒答
        if not reranked or max(c.score for c in reranked) < MIN_RERANK_SCORE:
            yield {
                "type": "done",
                "answer": REFUSE_ANSWER,
                "refused": True,
                "citations": [],
                "provider": "",
                "model": "",
            }
            return

        messages = [
            {
                "role": "system",
                "content": "你是 Oasis Curator 文档问答助手，只依据参考资料回答，实事求是。",
            },
            {"role": "user", "content": self._build_generation_prompt(question, reranked)},
        ]

        parts: List[str] = []
        async for token in self._llm.chat_stream(messages, temperature=0.3):
            parts.append(token)
            yield {"type": "token", "text": token}

        answer_text = "".join(parts)
        provider = self._llm.last_provider or ""
        model = ""
        refused = REFUSE_ANSWER in answer_text
        citations = [] if refused else self._extract_citations(answer_text)
        yield {
            "type": "done",
            "answer": answer_text,
            "refused": refused,
            "citations": citations,
            "provider": provider,
            "model": model,
        }


# 模块级实例：供 API 与脚本直接使用
rag_pipeline = RagPipeline()
