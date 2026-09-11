"""
文档模型 (Document)

记录上传文档的元信息。正文经切分、向量化后存入 ChromaDB，
chunk 的向量元数据携带 doc_id / tenant_id / visibility 与本文档关联，
删除文档时同时清理向量库数据。

可见性（visibility）：tenant 租户内公开 / private 仅上传者可见 / roles 指定角色可见
（判定规则见 core/doc_permission.py，向量检索与文档列表共用）
"""

import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False, index=True
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pdf/word/txt/markdown
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_strategy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="paragraphs"
    )
    # 可见性：tenant / private / roles
    visibility: Mapped[str] = mapped_column(
        String(20), nullable=False, default="tenant", index=True
    )
    # roles 可见性下的角色编码（逗号分隔，与向量元数据保持同一格式）
    allowed_roles: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    uploader_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<Document(id={self.id}, name={self.file_name}, "
            f"chunks={self.chunk_count}, visibility={self.visibility})>"
        )
