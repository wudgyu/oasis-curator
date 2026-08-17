"""
认证 API 路由

- POST /api/auth/login    — 登录，返回 JWT Token
- POST /api/auth/logout   — 登出
- GET  /api/auth/me       — 获取当前用户信息（含可访问租户列表）

依赖注入：
- get_current_user       — 从 Bearer Token 解析当前用户
- get_current_tenant_id  — 从 X-Tenant-Id 请求头解析上下文租户（默认主租户）
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.user_tenant import UserTenant
from app.schemas.auth import LoginRequest, TokenResponse, UserInfoResponse, TenantBrief
from app.core.security import verify_password, create_access_token, decode_access_token

router = APIRouter(prefix="/api/auth", tags=["认证"])

# HTTP Bearer Token 认证方案
security_scheme = HTTPBearer()

# 上下文租户请求头
TENANT_HEADER = "X-Tenant-Id"


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    从请求头 Authorization: Bearer <token> 中解析当前用户

    用于后续需要认证的接口依赖注入
    """
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id: Optional[str] = payload.get("user_id")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 中缺少用户标识",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if user.status == "disabled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用",
        )

    return user


def get_accessible_tenant_ids(db: Session, user: User) -> list:
    """
    获取用户可访问的全部租户 ID（主租户 + 关联租户，去重）
    """
    ids = [user.tenant_id]
    for row in db.query(UserTenant.tenant_id).filter(UserTenant.user_id == user.id).all():
        if row[0] not in ids:
            ids.append(row[0])
    return ids


def get_current_tenant_id(
    current_user: User = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> str:
    """
    解析当前上下文租户 ID

    - 未携带 X-Tenant-Id 请求头 → 返回用户主租户
    - 携带时校验用户是否有该租户的访问权限，无权限返回 403
    """
    if x_tenant_id is None:
        return current_user.tenant_id

    if x_tenant_id not in get_accessible_tenant_ids(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该租户",
        )
    return x_tenant_id


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """
    使用用户名和密码登录，返回 JWT Access Token。

    Token 包含 user_id、tenant_id、role，有效期 24 小时。
    """
    # 查找用户
    user = db.query(User).filter(User.username == body.username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 验证密码
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 检查用户状态
    if user.status == "disabled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用，请联系管理员",
        )

    # 生成 Token
    access_token = create_access_token(
        data={
            "user_id": user.id,
            "tenant_id": user.tenant_id,
            "role": user.role,
        }
    )

    return TokenResponse(access_token=access_token)


@router.post("/logout", summary="用户登出")
def logout(current_user: User = Depends(get_current_user)):
    """
    登出接口。

    JWT 无状态，登出由客户端丢弃 Token 实现。
    服务端仅校验身份，确认当前用户有效即返回成功。
    """
    return {"message": "已登出", "username": current_user.username}


@router.get("/me", response_model=UserInfoResponse, summary="获取当前用户信息")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    返回当前登录用户的详细信息，包含可访问的租户列表。
    """
    # 查询主租户名称
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()

    # 查询可访问租户列表（主租户在前 + 关联租户）
    accessible_ids = get_accessible_tenant_ids(db, current_user)
    tenant_map = (
        {t.id: t.name for t in db.query(Tenant).filter(Tenant.id.in_(accessible_ids)).all()}
        if accessible_ids
        else {}
    )
    tenant_briefs = [
        TenantBrief(id=tid, name=tenant_map[tid])
        for tid in accessible_ids
        if tid in tenant_map
    ]

    return UserInfoResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        tenant_id=current_user.tenant_id,
        tenant_name=tenant.name if tenant else "",
        role=current_user.role,
        status=current_user.status,
        tenants=tenant_briefs,
    )