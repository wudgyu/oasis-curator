"""
用户管理 API 路由（RBAC 数据范围）

- GET    /api/users      — 分页查询（按角色数据范围过滤）
- POST   /api/users      — 在指定组织创建用户并配置角色
- PUT    /api/users/{id} — 修改用户信息/角色/状态/所属组织
- DELETE /api/users/{id} — 删除用户

数据范围（get_data_scope）：
- admin:     上下文租户内全部
- manager:   本组织 + 子组织（可写）
- auditor:   本组织 + 子组织（只读）
- employee:  仅本组织（只读）

防护规则：
- 任何人不能修改自己的角色/状态、不能删除自己
- 根组织最后一名 manager 保底（防租户失管）
- 平台管理员账号（tenant_id IS NULL）不受租户 manager 管辖
"""

import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.role import Role
from app.models.organization import Organization
from app.schemas.user import UserCreate, UserUpdate, UserResponse, UserListResponse
from app.core.security import hash_password
from app.core.permission import get_data_scope, get_role_code, can_manage_org, can_manage_user
from app.api.auth import get_current_user, require_context_tenant_id

router = APIRouter(prefix="/api/users", tags=["用户管理"])

# 可通过本 API 分配的角色（admin 为平台内置，不在此列）
ASSIGNABLE_ROLES = ("manager", "auditor", "employee")


def org_to_response(org: Organization):
    """组织 ORM → OrgResponse（复用 org schema）"""
    from app.schemas.org import OrgResponse
    return OrgResponse(
        id=org.id, name=org.name, path=org.path, parent_id=org.parent_id,
        tenant_id=org.tenant_id, created_at=org.created_at, updated_at=org.updated_at,
    )


def user_to_response(user: User, org: Organization, role_code: str) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        org=org_to_response(org),
        role_code=role_code,
        status=user.status,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def resolve_role(db: Session, role_code: str) -> Role:
    """校验并返回可分配角色"""
    role = db.query(Role).filter(Role.code == role_code, Role.tenant_id.is_(None)).first()
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的角色：{role_code}",
        )
    return role


def get_root_org(db: Session, tenant_id: str) -> Organization:
    """获取租户根组织"""
    return (
        db.query(Organization)
        .filter(Organization.tenant_id == tenant_id, Organization.parent_id.is_(None))
        .first()
    )


def guard_last_root_manager(db: Session, user: User, new_role_code: Optional[str]) -> None:
    """
    根组织最后一名 manager 保底：
    降权/删除/迁移根组织 manager 前，根组织必须仍保留至少一名 manager。
    """
    if user.tenant_id is None or user.org_id is None:
        return  # 平台管理员不适用
    root = get_root_org(db, user.tenant_id)
    if root is None or user.org_id != root.id:
        return  # 非根组织用户不适用

    role_code = get_role_code(user, db)
    # 目标用户当前是根组织 manager，且即将不再是 manager
    if role_code == "manager" and new_role_code != "manager":
        manager_role = db.query(Role).filter(Role.code == "manager").first()
        manager_count = (
            db.query(User)
            .filter(User.org_id == root.id, User.role_id == manager_role.id,
                    User.status == "active")
            .count()
        )
        if manager_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="根组织至少需要保留一名经理，无法执行该操作",
            )


@router.get("", response_model=UserListResponse, summary="分页查询用户列表")
def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    username: str = Query("", description="按用户名模糊搜索"),
    role: str = Query("", description="按角色筛选"),
    status_filter: str = Query("", alias="status", description="按状态筛选"),
    org_id: str = Query("", description="按组织筛选"),
    include_children: bool = Query(False, description="组织筛选是否含子组织"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context_tenant_id: str = Depends(require_context_tenant_id),
):
    """分页查询用户列表，自动按当前用户角色的数据范围过滤"""
    query = db.query(User, Organization).join(
        Organization, User.org_id == Organization.id
    ).filter(User.tenant_id == context_tenant_id)

    # 角色数据范围
    scope = get_data_scope(current_user, db)
    if scope.type == "org_only":
        query = query.filter(User.org_id == scope.org_id)
    elif scope.type == "subtree":
        query = query.filter(Organization.path.like(f"{scope.path_prefix}%"))
    # GLOBAL 不过滤

    # 条件筛选
    if username:
        query = query.filter(User.username.contains(username))
    if role:
        query = query.join(Role, User.role_id == Role.id).filter(Role.code == role)
    if status_filter:
        query = query.filter(User.status == status_filter)
    if org_id:
        if include_children:
            target = db.query(Organization).filter(Organization.id == org_id).first()
            if target is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="组织不存在")
            query = query.filter(Organization.path.like(f"{target.path}%"))
        else:
            query = query.filter(User.org_id == org_id)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    rows = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    # 批量查询角色 code
    role_ids = {u.role_id for u, _ in rows}
    role_map = {r.id: r.code for r in db.query(Role).filter(Role.id.in_(role_ids)).all()}

    return UserListResponse(
        items=[
            user_to_response(u, org, role_map.get(u.role_id, ""))
            for u, org in rows
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
    current_user: User = Depends(get_current_user),
    context_tenant_id: str = Depends(require_context_tenant_id),
):
    """在指定组织创建用户并配置角色（admin / 子树内 manager）"""
    # 目标组织校验
    org = db.query(Organization).filter(Organization.id == body.org_id).first()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="组织不存在")
    if org.tenant_id != context_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="目标组织不属于上下文租户",
        )
    if not can_manage_org(current_user, db, org):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限在该组织下创建用户",
        )

    # 用户名租户内唯一
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

    role = resolve_role(db, body.role_code)
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        tenant_id=context_tenant_id,
        org_id=org.id,
        role_id=role.id,
        status=body.status,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_response(user, org, role.code)


@router.put("/{user_id}", response_model=UserResponse, summary="编辑用户")
def update_user(
    user_id: str,
    body: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context_tenant_id: str = Depends(require_context_tenant_id),
):
    """修改用户信息（admin / 子树内 manager；任何人不能改自己的角色与状态）"""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.tenant_id != context_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户不属于上下文租户",
        )
    if not can_manage_user(current_user, db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限编辑该用户",
        )

    # 不能修改自己的角色/状态
    if user.id == current_user.id and (body.role_code is not None or body.status is not None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能修改自己的角色或状态",
        )

    # 根组织最后一名 manager 保底
    if body.role_code is not None or body.org_id is not None or body.status == "disabled":
        new_role = body.role_code
        if body.role_code is None:
            new_role = get_role_code(user, db)
        guard_last_root_manager(db, user, new_role)

    # 更新所属组织
    org = db.query(Organization).filter(Organization.id == user.org_id).first()
    if body.org_id is not None and body.org_id != user.org_id:
        new_org = db.query(Organization).filter(Organization.id == body.org_id).first()
        if new_org is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="组织不存在")
        if new_org.tenant_id != context_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="目标组织不属于上下文租户",
            )
        if not can_manage_org(current_user, db, new_org):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限将用户迁移到该组织",
            )
        user.org_id = new_org.id
        org = new_org

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
    if body.status is not None:
        user.status = body.status

    role_code = get_role_code(user, db)
    if body.role_code is not None:
        role = resolve_role(db, body.role_code)
        user.role_id = role.id
        role_code = role.code

    db.commit()
    db.refresh(user)
    return user_to_response(user, org, role_code)


@router.delete("/{user_id}", summary="删除用户")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context_tenant_id: str = Depends(require_context_tenant_id),
):
    """删除用户（admin / 子树内 manager；不能删除自己）"""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
    if user.tenant_id != context_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户不属于上下文租户",
        )
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="不能删除当前登录用户",
        )
    if not can_manage_user(current_user, db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限删除该用户",
        )

    # 根组织最后一名 manager 保底
    guard_last_root_manager(db, user, None)

    db.delete(user)
    db.commit()
    return {"message": f"已删除用户「{user.username}」"}