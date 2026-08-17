"""
租户相关 Pydantic 模型

- TenantCreate / TenantUpdate: 请求体
- TenantResponse / TenantListResponse: 响应体
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    """创建租户请求"""
    name: str = Field(..., min_length=1, max_length=100, description="租户名称")
    plan: str = Field(default="basic", pattern="^(basic|pro|enterprise)$", description="套餐类型")
    status: str = Field(default="active", pattern="^(active|disabled)$", description="状态")


class TenantUpdate(BaseModel):
    """更新租户请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="租户名称")
    plan: Optional[str] = Field(None, pattern="^(basic|pro|enterprise)$", description="套餐类型")
    status: Optional[str] = Field(None, pattern="^(active|disabled)$", description="状态")


class TenantResponse(BaseModel):
    """单个租户响应"""
    id: str
    name: str
    plan: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    """分页租户列表响应"""
    items: list[TenantResponse]
    total: int
    page: int
    page_size: int
    total_pages: int