"""
会话与消息 请求/响应 Schema
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class ConversationCreate(BaseModel):
    """新建会话请求"""

    title: Optional[str] = Field(
        default=None, max_length=100, description="会话标题，缺省为「新会话」"
    )


class ConversationItem(BaseModel):
    """会话列表单项"""

    id: str
    title: str
    message_count: int = Field(description="消息条数（含提问与回答）")
    created_at: datetime
    updated_at: datetime


class MessageSource(BaseModel):
    """消息引用的原文片段（重排序保留的候选块）"""

    score: int = Field(description="重排序打分 1-10")
    text: str = Field(description="文本块内容（截断）")
    source_file: str
    chunk_index: int
    page: Optional[int] = None


class MessageItem(BaseModel):
    """消息单项"""

    id: str
    role: str = Field(description="user / assistant")
    content: str
    refused: bool = Field(default=False, description="助手是否判定文档中无答案")
    citations: List[str] = Field(default_factory=list, description="引用来源")
    sources: List[MessageSource] = Field(
        default_factory=list, description="引用对应的原文片段（点击引用时展示）"
    )
    created_at: datetime


class ConversationDetail(BaseModel):
    """会话详情（含消息列表）"""

    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: List[MessageItem] = Field(default_factory=list)


class StreamAskRequest(BaseModel):
    """流式问答请求"""

    question: str = Field(min_length=1, max_length=1000, description="用户问题")
    conversation_id: Optional[str] = Field(
        default=None, description="会话 ID；缺省则新建会话"
    )
    doc_id: Optional[str] = Field(default=None, description="可选，限定单文档检索")
