"""
角色 API 路由

- GET /api/roles — 可分配角色列表（当前为 3 个内置租户角色）

角色当前为全局内置、固定不变，不提供自定义配置入口；
roles 表已预留 tenant_id 字段，后续支持租户自定义角色。
"""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.role import Role
from app.models.user import User
from app.schemas.user import RoleOption
from app.api.auth import get_current_user

router = APIRouter(prefix="/api/roles", tags=["角色"])


@router.get("", response_model=List[RoleOption], summary="查询可分配角色列表")
def list_roles(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """
    返回可分配角色列表（manager / auditor / employee）。

    平台 admin 角色不在此列——它由平台内部管理，不可通过业务 API 分配。
    """
    roles = (
        db.query(Role)
        .filter(Role.tenant_id.is_(None), Role.code != "admin")
        .order_by(Role.code)
        .all()
    )
    return [RoleOption(code=r.code, name=r.name) for r in roles]