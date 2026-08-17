"""
用户-租户关联模型 (UserTenant)

一个用户可以访问多个租户（主租户 + 关联租户）。
关联租户仅表示"可见/可管理"范围，用户的角色仍是全局的。
"""

from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserTenant(Base):
    __tablename__ = "user_tenants"

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def __repr__(self) -> str:
        return f"<UserTenant(user_id={self.user_id}, tenant_id={self.tenant_id})>"