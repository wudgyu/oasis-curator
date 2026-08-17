"""
组织模型 (Organization)

租户内的树形结构单元：
- parent_id 自关联形成组织树，NULL = 根组织
- path 为物化路径（'/{id1}/{id2}/'），路径段使用不可变 UUID，
  子树查询通过 `path LIKE '{prefix}%'` 前缀匹配实现
- 每个租户创建时自动生成根组织
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=False, index=True
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # 物化路径：'/{id1}/{id2}/{id3}/'，首尾均有 '/'
    path: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name={self.name}, path={self.path})>"