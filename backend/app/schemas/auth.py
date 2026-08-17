"""
认证相关 Pydantic 模型

- LoginRequest: 登录请求
- TokenResponse: 登录成功返回的 Token
- UserInfoResponse: 当前用户信息
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class TokenResponse(BaseModel):
    """登录成功返回"""
    access_token: str = Field(..., description="JWT Access Token")
    token_type: str = Field(default="bearer", description="Token 类型")


class UserInfoResponse(BaseModel):
    """当前用户信息（/api/auth/me 返回）"""
    id: str
    username: str
    email: str
    tenant_id: str
    tenant_name: str = ""
    role: str
    status: str

    class Config:
        from_attributes = True