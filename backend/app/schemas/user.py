"""
用户相关 Pydantic 模型

- UserCreate / UserUpdate: 请求体
- UserResponse / UserListResponse: 响应体
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    role: str = Field(default="viewer", pattern="^(admin|editor|viewer)$", description="角色")
    status: str = Field(default="active", pattern="^(active|disabled)$", description="状态")
    # 可访问的其它租户 ID（主租户 = 创建时的上下文租户）
    tenant_ids: Optional[List[str]] = Field(None, description="可访问的其它租户 ID 列表")


class UserUpdate(BaseModel):
    """更新用户请求（所有字段可选）"""
    username: Optional[str] = Field(None, min_length=1, max_length=50, description="用户名")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    password: Optional[str] = Field(None, min_length=6, max_length=128, description="密码")
    role: Optional[str] = Field(None, pattern="^(admin|editor|viewer)$", description="角色")
    status: Optional[str] = Field(None, pattern="^(active|disabled)$", description="状态")
    # 可访问的其它租户 ID 列表（提交时整体替换）
    tenant_ids: Optional[List[str]] = Field(None, description="可访问的其它租户 ID 列表")


class UserResponse(BaseModel):
    """单个用户响应（不返回密码哈希）"""
    id: str
    username: str
    email: str
    tenant_id: str
    tenant_name: str = ""
    role: str
    status: str
    created_at: datetime
    updated_at: datetime
    # 可访问的其它租户 ID（不含主租户）
    tenant_ids: List[str] = []

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """分页用户列表响应"""
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int