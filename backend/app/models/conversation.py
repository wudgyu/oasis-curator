"""
会话与消息模型（问答历史）

- Conversation：一次问答会话，归属具体用户（仅本人可见）
- ChatMessage：会话内的一条消息（用户提问 / 助手回答），
  助手回答附带引用来源与拒答标记，供前端还原引用溯源
"""

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, DateTime, ForeignKey, Boolean, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False, default="新会话")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Conversation(id={self.id}, title={self.title})>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    conversation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    refused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 引用来源：["文件名, 第N段", ...]
    citations: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    # 重排序保留的候选块（含原文片段），供前端点击引用时展示原文
    sources: Mapped[Optional[List[dict]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<ChatMessage(id={self.id}, role={self.role})>"
