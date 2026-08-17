"""
用户管理 API 路由

- GET    /api/users      — 分页查询用户列表（租户隔离）
- POST   /api/users      — 新增用户（admin）
- PUT    /api/users/{id} — 编辑用户（admin）
- DELETE /api/users/{id} — 删除用户（admin）

权限模型：
- admin: 可管理本租户所有用户
- editor: 可查看本租户所有用户
- viewer: 只能查看自己的信息
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.tenant import Tenant
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserListResponse
from app.core.security import hash_password
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/users", tags=["用户管理"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """权限校验：仅 admin 角色可执行写操作"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可执行此操作",
        )
    return current_user


def user_to_response(user: User, tenant_name: str = "") -> UserResponse:
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
):
    """
    分页查询用户列表。

    - admin / editor: 可查看本租户所有用户
    - viewer: 只能查看自己
    - 自动按当前用户所属租户过滤
    """
    # 租户隔离：仅查询当前用户所属租户
    query = db.query(User).filter(User.tenant_id == current_user.tenant_id)

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

    # 批量查询租户名称
    tenant_ids = {u.tenant_id for u in users}
    tenants = {t.id: t.name for t in db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).all()}

    return UserListResponse(
        items=[user_to_response(u, tenants.get(u.tenant_id, "")) for u in users],
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
):
    """
    新增用户，自动归属到当前管理员所在租户。

    用户名和邮箱在当前租户内唯一。
    """
    # 用户名唯一校验（租户范围内）
    existing = (
        db.query(User)
        .filter(User.tenant_id == current_user.tenant_id, User.username == body.username)
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
        tenant_id=current_user.tenant_id,
        role=body.role,
        status=body.status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 查询租户名称
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return user_to_response(user, tenant.name if tenant else "")


@router.put("/{user_id}", response_model=UserResponse, summary="编辑用户")
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    编辑用户信息，仅更新提交的字段。

    编辑范围受租户隔离限制：仅能编辑本租户用户。
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 租户隔离：不能编辑其他租户的用户
    if user.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不能编辑其他租户的用户",
        )

    # 更新用户名时检查唯一性
    if body.username is not None and body.username != user.username:
        existing = (
            db.query(User)
            .filter(User.tenant_id == current_user.tenant_id, User.username == body.username)
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

    db.commit()
    db.refresh(user)

    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    return user_to_response(user, tenant.name if tenant else "")


@router.delete("/{user_id}", summary="删除用户")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    删除用户。

    限制：不能删除自己，不能删除其他租户的用户。
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # 租户隔离
    if user.tenant_id != current_user.tenant_id:
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