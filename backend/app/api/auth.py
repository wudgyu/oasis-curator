"""
认证 API 路由

- POST /api/auth/login    — 登录，返回 JWT Token
- POST /api/auth/logout   — 登出
- GET  /api/auth/me       — 获取当前用户信息（RBAC 新结构）

依赖注入：
- get_current_user        — 从 Bearer Token 解析当前用户（含角色）
- get_context_tenant_id   — 解析上下文租户（admin 显式指定，普通用户固定为自身租户）
- require_context_tenant_id — 要求必须携带上下文租户（组织/用户管理接口用）
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.organization import Organization
from app.schemas.auth import LoginRequest, TokenResponse, UserInfoResponse, TenantBrief, OrgBrief
from app.core.security import verify_password, create_access_token, decode_access_token
from app.core.permission import get_role_code

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

    用于后续需要认证的接口依赖注入。
    每次请求从数据库实时加载用户与角色，角色变更立即生效。
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


def get_context_tenant_id(
    current_user: User = Depends(get_current_user),
    x_tenant_id: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[str]:
    """
    解析当前上下文租户 ID：

    - 平台 admin：以 X-Tenant-Id 为准（需存在），未携带返回 None（由调用方决定是否必须）
    - 普通用户：固定为自身租户；伪造 X-Tenant-Id（不等于自身租户）返回 403
    """
    role_code = get_role_code(current_user, db)
    if role_code == "admin":
        if x_tenant_id is None:
            return None
        tenant = db.query(Tenant).filter(Tenant.id == x_tenant_id).first()
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="上下文租户不存在",
            )
        return x_tenant_id

    # 普通用户
    if x_tenant_id is not None and x_tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权访问该租户",
        )
    return current_user.tenant_id


def require_context_tenant_id(
    context_tenant_id: Optional[str] = Depends(get_context_tenant_id),
) -> str:
    """组织/用户管理接口必须携带上下文租户（admin 场景下强制 X-Tenant-Id）"""
    if context_tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少上下文租户（X-Tenant-Id 请求头）",
        )
    return context_tenant_id


@router.post("/login", response_model=TokenResponse, summary="用户登录")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """
    使用用户名和密码登录，返回 JWT Access Token。

    用户名在租户内唯一，可能出现平台管理员与租户用户同名的情况：
    密码匹配且唯一命中时登录成功。
    """
    # 用户名可能命中多个（平台管理员 + 各租户同名用户），逐个验证密码
    candidates = db.query(User).filter(User.username == body.username).all()
    matched: Optional[User] = None
    for user in candidates:
        if verify_password(body.password, user.password_hash):
            if matched is not None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="账号存在冲突，请联系管理员",
                )
            matched = user

    if matched is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if matched.status == "disabled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被禁用，请联系管理员",
        )

    # 生成 Token
    role_code = get_role_code(matched, db)
    access_token = create_access_token(
        data={
            "user_id": matched.id,
            "tenant_id": matched.tenant_id,
            "role": role_code,
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
    返回当前登录用户信息：role_code + 所属租户/组织（平台管理员为 null）。
    """
    role_code = get_role_code(current_user, db)

    tenant_brief = None
    org_brief = None
    if current_user.tenant_id is not None:
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        if tenant is not None:
            tenant_brief = TenantBrief(id=tenant.id, name=tenant.name)
    if current_user.org_id is not None:
        org = db.query(Organization).filter(Organization.id == current_user.org_id).first()
        if org is not None:
            org_brief = OrgBrief(id=org.id, name=org.name, path=org.path)

    return UserInfoResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role_code=role_code,
        status=current_user.status,
        tenant=tenant_brief,
        org=org_brief,
    )