"""
RAG 问答 请求与响应 Schema
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class QaAskRequest(BaseModel):
    """问答请求"""

    question: str = Field(min_length=1, max_length=1000, description="用户问题")
    doc_id: Optional[str] = Field(
        default=None, description="可选，限定在指定文档内检索"
    )


class RerankedChunkItem(BaseModel):
    """重排序后的候选块（含 LLM 打分，便于前端展示决策过程）"""

    score: int = Field(description="LLM 相关性打分 1-10")
    reason: str = Field(default="", description="打分理由")
    text: str = Field(description="文本块内容（截断）")
    source_file: str
    chunk_index: int
    page: Optional[int] = None


class QaAskResponse(BaseModel):
    """问答结果"""

    answer: str
    refused: bool = Field(description="是否判定文档中无答案（拒答）")
    citations: List[str] = Field(description="回答中标注的引用 [文件名, 第N段]")
    retrieved_count: int = Field(description="向量检索命中条数")
    reranked: List[RerankedChunkItem] = Field(description="重排序后保留的候选块")
    provider: str = Field(description="实际应答的 LLM provider")
    model: str = Field(description="实际应答的模型名")
