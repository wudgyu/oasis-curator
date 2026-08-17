"""
用户管理 API 路由

- GET    /api/users      — 分页查询用户列表（按上下文租户隔离）
- POST   /api/users      — 新增用户（admin，归属上下文租户）
- PUT    /api/users/{id} — 编辑用户（admin，上下文租户内）
- DELETE /api/users/{id} — 删除用户（admin，上下文租户内）

上下文租户：通过 X-Tenant-Id 请求头切换（见 get_current_tenant_id），
未携带时默认为用户主租户。

权限模型：
- admin: 可管理上下文租户的所有用户
- editor: 可查看上下文租户的所有用户
- viewer: 只能查看自己
"""

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.models.user_tenant import UserTenant
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserListResponse
from app.core.security import hash_password
from app.api.auth import get_current_user, get_current_tenant_id

router = APIRouter(prefix="/api/users", tags=["用户管理"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """权限校验：仅 admin 角色可执行写操作"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可执行此操作",
        )
    return current_user


def get_user_tenant_ids(db: Session, user_id: str) -> list:
    """查询用户关联的其它租户 ID（不含主租户）"""
    return [
        row[0]
        for row in db.query(UserTenant.tenant_id)
        .filter(UserTenant.user_id == user_id)
        .all()
    ]


def sync_user_tenants(db: Session, user_id: str, tenant_ids: list) -> None:
    """整体替换用户的可访问租户关联（去除主租户重复项）"""
    db.query(UserTenant).filter(UserTenant.user_id == user_id).delete()
    for tid in tenant_ids:
        db.add(UserTenant(user_id=user_id, tenant_id=tid))


def user_to_response(
    user: User, tenant_name: str = "", tenant_ids: Optional[list] = None
) -> UserResponse:
    """将 ORM 模型转换为响应 Schema"""
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        tenant_id=user.tenant_id,
        tenant_name=tenant_name,
        role=user.role,
        status=user.status,
        created_at=user.created_at,
        updated_at=user.updated_at,
        tenant_ids=tenant_ids if tenant_ids is not None else [],
    )


@router.get("", response_model=UserListResponse, summary="分页查询用户列表")
def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    username: str = Query("", description="按用户名模糊搜索"),
    role: str = Query("", description="按角色筛选"),
    status_filter: str = Query("", alias="status", description="按状态筛选"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context_tenant_id: str = Depends(get_current_tenant_id),
):
    """
    分页查询用户列表。

    - admin / editor: 可查看上下文租户的所有用户
    - viewer: 只能查看自己
    - 按上下文租户（X-Tenant-Id）过滤
    """
    # 租户隔离：仅查询上下文租户
    query = db.query(User).filter(User.tenant_id == context_tenant_id)

    # viewer 只能看自己
    if current_user.role == "viewer":
        query = query.filter(User.id == current_user.id)

    if username:
        query = query.filter(User.username.contains(username))
    if role:
        query = query.filter(User.role == role)
    if status_filter:
        query = query.filter(User.status == status_filter)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    users = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 批量查询租户名称与关联租户
    tenant_ids = {u.tenant_id for u in users}
    tenants = {t.id: t.name for t in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()}
    user_ids = [u.id for u in users]
    assoc_map: dict = {uid: [] for uid in user_ids}
    for row in db.query(UserTenant).filter(UserTenant.user_id.in_(user_ids)).all():
        assoc_map[row.user_id].append(row.tenant_id)

    return UserListResponse(
        items=[
            user_to_response(u, tenants.get(u.tenant_id, ""), assoc_map.get(u.id, []))
            for u in users
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="新增用户")
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    context_tenant_id: str = Depends(get_current_tenant_id),
):
    """
    新增用户，归属到当前上下文租户。

    用户名在上下文租户内唯一；tenant_ids 指定可访问的其它租户。
    """
    # 用户名唯一校验（上下文租户范围内）
    existing = (
        db.query(User)
        .filter(User.tenant_id == context_tenant_id, User.username == body.username)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"用户名「{body.username}」在当前租户中已存在",
        )

    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        tenant_id=context_tenant_id,
        role=body.role,
        status=body.status,
    )
    db.add(user)
    db.flush()  # 先获取 user.id

    # 建立可访问租户关联（排除主租户自身）
    extra_ids = [tid for tid in (body.tenant_ids or []) if tid != context_tenant_id]
    sync_user_tenants(db, user.id, extra_ids)

    db.commit()
    db.refresh(user)

    # 查询租户名称
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return user_to_response(user, tenant.name if tenant else "", extra_ids)


@router.put("/{user_id}", response_model=UserResponse, summary="编辑用户")
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    context_tenant_id: str = Depends(get_current_tenant_id),
):
    """
    编辑用户信息，仅更新提交的字段。

    编辑范围受租户隔离限制：仅能编辑上下文租户的用户。
    tenant_ids 提交时整体替换用户的租户关联。
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 租户隔离：不能编辑上下文租户之外的用户
    if user.tenant_id != context_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能编辑其他租户的用户",
        )

    # 更新用户名时检查唯一性
    if body.username is not None and body.username != user.username:
        existing = (
            db.query(User)
            .filter(User.tenant_id == context_tenant_id, User.username == body.username)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"用户名「{body.username}」在当前租户中已存在",
            )
        user.username = body.username

    if body.email is not None:
        user.email = body.email
    if body.password is not None:
        user.password_hash = hash_password(body.password)
    if body.role is not None:
        user.role = body.role
    if body.status is not None:
        user.status = body.status

    # 更新租户关联
    extra_ids = []
    if body.tenant_ids is not None:
        extra_ids = [tid for tid in body.tenant_ids if tid != user.tenant_id]
        sync_user_tenants(db, user.id, extra_ids)

    db.commit()
    db.refresh(user)

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    current_extra_ids = extra_ids if body.tenant_ids is not None else get_user_tenant_ids(db, user.id)
    return user_to_response(user, tenant.name if tenant else "", current_extra_ids)


@router.delete("/{user_id}", summary="删除用户")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
    context_tenant_id: str = Depends(get_current_tenant_id),
):
    """
    删除用户。

    限制：不能删除自己，不能删除上下文租户之外的用户。
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 租户隔离
    if user.tenant_id != context_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能删除其他租户的用户",
        )

    # 不能删除自己
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除当前登录用户",
        )

    db.delete(user)
    db.commit()

    return {"message": f"已删除用户「{user.username}」"}