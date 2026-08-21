"""
IAM 配置生成器 API 路由

- GET  /api/iam/templates      — 查询预设权限模板列表
- POST /api/iam/generate-role  — 自然语言 → IAM 角色配置 JSON
- POST /api/iam/save-role      — 保存生成的配置到数据库
- GET  /api/iam/roles          — 查询当前租户所有角色（含内置 + 自定义）
- DELETE /api/iam/roles/{id}   — 删除自定义角色

权限：仅 admin 角色可访问；生成/保存的角色配置绑定上下文租户。
"""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user, require_context_tenant_id
from app.core.iam_config import IamConfigGenerator
from app.core.permission import get_role_code
from app.database import get_db
from app.models.role import Role
from app.models.user import User
from app.schemas.iam_config import (
    IamGenerateRequest,
    IamGenerateResponse,
    IamRoleItem,
    IamSaveRoleRequest,
    IamSaveRoleResponse,
    IamTemplateInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/iam", tags=["IAM 配置生成"])

_generator = IamConfigGenerator()


def _require_admin(user: User, db: Session) -> None:
    """校验当前用户为平台 admin，否则 403"""
    if get_role_code(user, db) != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可管理 IAM 配置",
        )


@router.get("/templates", response_model=List[IamTemplateInfo], summary="查询预设权限模板")
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """返回预设的常见权限模板（全局只读/部门管理员/审计员等）"""
    _require_admin(current_user, db)
    return IamConfigGenerator.list_templates()


@router.post(
    "/generate-role",
    response_model=IamGenerateResponse,
    summary="自然语言生成 IAM 角色配置",
)
async def generate_role(
    request: IamGenerateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(require_context_tenant_id),
):
    """
    将自然语言权限需求转换为 IAM 角色配置 JSON。

    - Schema 校验失败自动重试（最多 2 次）
    - 同名角色冲突检测（当前租户命名空间）
    - 生成的角色配置绑定上下文租户
    """
    _require_admin(current_user, db)

    # 当前租户已存在的角色编码（多租户命名空间隔离：仅查本租户）
    existing_codes = [
        r.code
        for r in db.query(Role).filter(Role.tenant_id == tenant_id).all()
    ]

    try:
        config, metadata = await _generator.generate(
            user_input=request.requirement,
            tenant_id=tenant_id,
            existing_role_codes=existing_codes,
        )
    except ValueError as e:
        logger.error("IAM 配置生成失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        ) from e

    return IamGenerateResponse(
        config=config.model_dump(),
        template_matched=metadata["template_matched"],
        template_name=metadata["template_name"],
        retries=metadata["retries"],
        conflicts=metadata["conflicts"],
    )


# ---------------------------------------------------------------------------
# 角色保存 & 管理
# ---------------------------------------------------------------------------


@router.post("/save-role", response_model=IamSaveRoleResponse, summary="保存生成的 IAM 角色配置")
def save_role(
    request: IamSaveRoleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(require_context_tenant_id),
):
    """
    将 IAM 配置生成器产出的角色配置持久化到数据库。

    - 角色编码冲突时，如果 overwrite=True 则覆盖，否则拒绝
    - 自定义角色绑定当前租户，与内置角色（tenant_id=NULL）命名空间隔离
    """
    _require_admin(current_user, db)

    role_config = request.config.get("role", {})
    role_code = role_config.get("code", "")
    role_name = role_config.get("name", "")
    role_desc = role_config.get("description", "")

    if not role_code or not role_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="角色配置缺少 role.code 或 role.name",
        )

    # 冲突检测：同一租户下是否已有同名编码的自定义角色
    existing = (
        db.query(Role)
        .filter(Role.tenant_id == tenant_id, Role.code == role_code)
        .first()
    )

    overwritten = False
    if existing:
        if not request.overwrite:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"角色编码 '{role_code}' 已存在，如需覆盖请设置 overwrite=true",
            )
        # 覆盖已有角色
        existing.name = role_name
        existing.description = role_desc
        existing.permissions_config = request.config.get("permissions")
        existing.data_scope_config = request.config.get("data_scope")
        db.commit()
        db.refresh(existing)
        overwritten = True
        logger.info("覆盖自定义角色: %s (tenant=%s)", role_code, tenant_id)
        return IamSaveRoleResponse(
            id=existing.id, code=existing.code, name=existing.name, overwritten=True
        )

    # 新建自定义角色
    new_role = Role(
        code=role_code,
        name=role_name,
        tenant_id=tenant_id,
        builtin=False,
        description=role_desc,
        permissions_config=request.config.get("permissions"),
        data_scope_config=request.config.get("data_scope"),
    )
    db.add(new_role)
    db.commit()
    db.refresh(new_role)
    logger.info("创建自定义角色: %s (tenant=%s)", role_code, tenant_id)

    return IamSaveRoleResponse(
        id=new_role.id, code=new_role.code, name=new_role.name, overwritten=False
    )


@router.get("/roles", response_model=List[IamRoleItem], summary="查询角色列表")
def list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(require_context_tenant_id),
):
    """
    返回当前租户可见的所有角色：

    - 全局内置角色（admin / manager / auditor / employee）
    - 当前租户的自定义角色
    """
    _require_admin(current_user, db)

    roles = (
        db.query(Role)
        .filter(
            (Role.tenant_id.is_(None)) | (Role.tenant_id == tenant_id)
        )
        .order_by(Role.builtin.desc(), Role.created_at)
        .all()
    )

    return [
        IamRoleItem(
            id=r.id,
            code=r.code,
            name=r.name,
            description=r.description,
            builtin=r.builtin,
            tenant_id=r.tenant_id,
            permissions=r.permissions_config,
            data_scope=r.data_scope_config,
            created_at=r.created_at,
        )
        for r in roles
    ]


@router.delete("/roles/{role_id}", summary="删除自定义角色")
def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    tenant_id: str = Depends(require_context_tenant_id),
):
    """
    删除当前租户的自定义角色。

    内置角色（builtin=true）不可删除。
    """
    _require_admin(current_user, db)

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="角色不存在")

    if role.builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="内置角色不可删除"
        )

    if role.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="无权操作其他租户的角色"
        )

    db.delete(role)
    db.commit()
    logger.info("删除自定义角色: %s (tenant=%s)", role.code, tenant_id)
    return {"message": "角色已删除", "id": role_id}
