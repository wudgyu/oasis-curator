"""
租户管理 API 路由

- GET    /api/tenants      — 分页查询租户列表（admin）
- POST   /api/tenants      — 创建租户（admin）
- PUT    /api/tenants/{id} — 编辑租户（admin）
- DELETE /api/tenants/{id} — 删除租户（admin）
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.tenant import TenantCreate, TenantUpdate, TenantResponse, TenantListResponse
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/tenants", tags=["租户管理"])


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """权限校验：仅 admin 角色可访问"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可执行此操作",
        )
    return current_user


def tenant_to_response(tenant: Tenant) -> TenantResponse:
    """将 ORM 模型转换为响应 Schema"""
    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        plan=tenant.plan,
        status=tenant.status,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )


@router.get("", response_model=TenantListResponse, summary="分页查询租户列表")
def list_tenants(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页条数"),
    name: str = Query("", description="按名称模糊搜索"),
    plan: str = Query("", description="按套餐筛选"),
    status_filter: str = Query("", alias="status", description="按状态筛选"),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """分页查询租户列表，支持按名称、套餐、状态筛选"""
    query = db.query(Tenant)

    if name:
        query = query.filter(Tenant.name.contains(name))
    if plan:
        query = query.filter(Tenant.plan == plan)
    if status_filter:
        query = query.filter(Tenant.status == status_filter)

    total = query.count()
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    tenants = (
        query.order_by(Tenant.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return TenantListResponse(
        items=[tenant_to_response(t) for t in tenants],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED, summary="创建租户")
def create_tenant(
    body: TenantCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """创建新租户，租户名称必须唯一"""
    existing = db.query(Tenant).filter(Tenant.name == body.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"租户名称「{body.name}」已存在",
        )

    tenant = Tenant(name=body.name, plan=body.plan, status=body.status)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant_to_response(tenant)


@router.put("/{tenant_id}", response_model=TenantResponse, summary="编辑租户")
def update_tenant(
    tenant_id: str,
    body: TenantUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """编辑租户信息，仅更新提交的字段"""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="租户不存在",
        )

    # 更新名称时检查唯一性
    if body.name is not None and body.name != tenant.name:
        existing = db.query(Tenant).filter(Tenant.name == body.name).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"租户名称「{body.name}」已存在",
            )
        tenant.name = body.name
    if body.plan is not None:
        tenant.plan = body.plan
    if body.status is not None:
        tenant.status = body.status

    db.commit()
    db.refresh(tenant)
    return tenant_to_response(tenant)


@router.delete("/{tenant_id}", summary="删除租户")
def delete_tenant(
    tenant_id: str,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """
    删除租户及其下所有用户。

    注意：生产环境应改为软删除或要求先迁移用户。
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="租户不存在",
        )

    # 级联删除关联用户
    db.query(User).filter(User.tenant_id == tenant_id).delete()
    db.delete(tenant)
    db.commit()

    return {"message": f"已删除租户「{tenant.name}」及其关联用户"}