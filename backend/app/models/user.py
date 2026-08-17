"""
用户模型 (User)

RBAC 1:1:1 模型：用户唯一归属一个租户 + 一个组织 + 持有一个角色。
- 平台管理员（role.code = 'admin'）：tenant_id / org_id 均为 NULL，全局通行
- 普通用户：tenant_id / org_id 必填，数据范围由角色决定
- username 在租户内唯一（应用层校验）
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    # NULL = 平台管理员
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True, index=True
    )
    # NULL = 平台管理员
    org_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=True, index=True
    )
    role_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("roles.id"), nullable=False
    )
    username: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(100), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username})>"