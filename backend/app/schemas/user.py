"""
用户相关 Pydantic 模型（RBAC 新结构）

- UserCreate / UserUpdate: 请求体（org_id + role_code）
- UserResponse / UserListResponse: 响应体（含组织信息）
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.schemas.org import OrgResponse


class UserCreate(BaseModel):
    """创建用户请求"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    email: EmailStr = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    org_id: str = Field(..., description="所属组织 ID")
    role_code: str = Field(..., pattern="^(manager|auditor|employee)$", description="角色 code")
    status: str = Field(default="active", pattern="^(active|disabled)$", description="状态")


class UserUpdate(BaseModel):
    """更新用户请求（所有字段可选）"""
    username: Optional[str] = Field(None, min_length=1, max_length=50, description="用户名")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    password: Optional[str] = Field(None, min_length=6, max_length=128, description="密码")
    org_id: Optional[str] = Field(None, description="所属组织 ID")
    role_code: Optional[str] = Field(None, pattern="^(manager|auditor|employee)$", description="角色 code")
    status: Optional[str] = Field(None, pattern="^(active|disabled)$", description="状态")


class UserResponse(BaseModel):
    """单个用户响应（不返回密码哈希）"""
    id: str
    username: str
    email: str
    org: OrgResponse
    role_code: str
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """分页用户列表响应"""
    items: list[UserResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RoleOption(BaseModel):
    """可选角色项"""
    code: str
    name: str