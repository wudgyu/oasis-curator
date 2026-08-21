"""
角色模型 (Role)

内置全局角色（tenant_id = NULL）：admin / manager / auditor / employee
- admin:     平台管理员，全局通行
- manager:   本组织 + 所有子组织，可写
- auditor:   本组织 + 所有子组织，只读
- employee:  仅本组织（不含子组织），只读

租户自定义角色（tenant_id != NULL）：由 IAM 配置生成器创建，包含
完整的 RBAC 2.0 权限配置（permissions + data_scope）。
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Boolean, ForeignKey, JSON, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # NULL = 全局内置角色；非 NULL = 租户自定义角色
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("tenants.id"), nullable=True, index=True
    )
    builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 自定义角色扩展字段：存储 IAM 配置生成器产出的完整 RBAC 2.0 配置
    permissions_config: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="权限列表 [{resource, actions}]"
    )
    data_scope_config: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True, comment="数据范围配置 {type, locations, orgs, departments}"
    )
    description: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True, comment="角色描述"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<Role(id={self.id}, code={self.code})>"