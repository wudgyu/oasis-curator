"""
角色模型 (Role)

内置全局角色（tenant_id = NULL）：admin / manager / auditor / employee
- admin:     平台管理员，全局通行
- manager:   本组织 + 所有子组织，可写
- auditor:   本组织 + 所有子组织，只读
- employee:  仅本组织（不含子组织），只读

tenant_id 字段预留租户自定义角色扩展位（后续填充即租户角色）。
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # NULL = 全局内置角色；非 NULL = 租户自定义角色（预留）
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True, index=True
    )
    builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, code={self.code})>"