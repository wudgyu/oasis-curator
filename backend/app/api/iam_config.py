"""
IAM 配置生成器 API 路由

- GET  /api/iam/templates      — 查询预设权限模板列表
- POST /api/iam/generate-role  — 自然语言 → IAM 角色配置 JSON

权限：仅 admin 角色可访问；生成的角色配置绑定上下文租户。
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
            detail="仅管理员可生成 IAM 配置",
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
