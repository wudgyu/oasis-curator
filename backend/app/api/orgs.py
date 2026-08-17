"""
组织管理 API 路由（上下文租户内）

- GET    /api/orgs/tree    — 组织树（嵌套结构，含用户数统计）
- POST   /api/orgs         — 在父组织下创建子组织
- PUT    /api/orgs/{id}    — 重命名
- POST   /api/orgs/{id}/move — 移动组织（防环 + 事务重写子树 path）
- DELETE /api/orgs/{id}    — 删除（仅空组织；根组织不可删）

权限：
- 读取：所有角色
- 写入：admin（上下文租户内任意位置）/ manager（限本组织子树内）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.models.organization import Organization
from app.schemas.org import OrgCreate, OrgUpdate, OrgMoveRequest, OrgResponse, OrgTreeNode
from app.api.auth import get_current_user, require_context_tenant_id
from app.core.permission import (
    get_role_code, get_user_org, can_manage_org, build_child_path, move_organization,
)

router = APIRouter(prefix="/api/orgs", tags=["组织管理"])


def get_org_or_404(db: Session, org_id: str) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="组织不存在")
    return org


def require_write_org(
    org: Organization,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Organization:
    """写操作权限校验：admin 或（manager 且组织在其子树内）"""
    if not can_manage_org(current_user, db, org):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限操作该组织",
        )
    return org


def build_tree(db: Session, tenant_id: str) -> list:
    """构建组织树（嵌套结构）"""
    orgs = (
        db.query(Organization)
        .filter(Organization.tenant_id == tenant_id)
        .order_by(Organization.path)
        .all()
    )
    nodes = {o.id: OrgTreeNode(
        id=o.id, name=o.name, path=o.path, parent_id=o.parent_id, children=[]
    ) for o in orgs}

    # 统计每个组织的直属用户数
    for user in db.query(User).filter(User.tenant_id == tenant_id, User.org_id.isnot(None)).all():
        node = nodes.get(user.org_id)
        if node is not None:
            node.user_count += 1

    roots: list = []
    for o in orgs:
        node = nodes[o.id]
        if o.parent_id is not None and o.parent_id in nodes:
            nodes[o.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


@router.get("/tree", response_model=list, summary="查询组织树")
def get_org_tree(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    context_tenant_id: str = Depends(require_context_tenant_id),
):
    """返回上下文租户的完整组织树（所有角色可读）"""
    return build_tree(db, context_tenant_id)


@router.post("", response_model=OrgResponse, status_code=status.HTTP_201_CREATED, summary="创建子组织")
def create_org(
    body: OrgCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context_tenant_id: str = Depends(require_context_tenant_id),
):
    """在 parent_id 下创建子组织（admin / 子树内 manager）"""
    parent = get_org_or_404(db, body.parent_id)
    if parent.tenant_id != context_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="父组织不属于上下文租户",
        )
    if not can_manage_org(current_user, db, parent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限在该组织下创建子组织",
        )

    # 同父组织下名称唯一
    existing = (
        db.query(Organization)
        .filter(Organization.parent_id == parent.id, Organization.name == body.name)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"同级组织下已存在「{body.name}」",
        )

    org = Organization(
        tenant_id=context_tenant_id,
        parent_id=parent.id,
        name=body.name,
        path="",  # 先占位，flushing 后回填（见下）
    )
    db.add(org)
    db.flush()  # 获取自增... UUID 由应用层默认生成，flush 后回填 path
    # path 依赖自身 id，flush 后 id 已生成
    org.path = build_child_path(parent.path, org.id)
    db.commit()
    db.refresh(org)
    return org


@router.put("/{org_id}", response_model=OrgResponse, summary="重命名组织")
def rename_org(
    org_id: str,
    body: OrgUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _context_tenant_id: str = Depends(require_context_tenant_id),
):
    """重命名组织（admin / 子树内 manager）"""
    org = get_org_or_404(db, org_id)
    if not can_manage_org(current_user, db, org):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限操作该组织",
        )

    if body.name != org.name:
        existing = (
            db.query(Organization)
            .filter(Organization.parent_id == org.parent_id, Organization.name == body.name)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"同级组织下已存在「{body.name}」",
            )
    org.name = body.name
    db.commit()
    db.refresh(org)
    return org


@router.post("/{org_id}/move", response_model=OrgResponse, summary="移动组织")
def move_org(
    org_id: str,
    body: OrgMoveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    context_tenant_id: str = Depends(require_context_tenant_id),
):
    """移动组织到新父组织（admin / 目标与新父组织均在 manager 子树内）"""
    org = get_org_or_404(db, org_id)
    new_parent = get_org_or_404(db, body.new_parent_id)

    if org.parent_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="根组织不可移动")
    if new_parent.tenant_id != context_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="新父组织不属于上下文租户",
        )
    if not can_manage_org(current_user, db, org) or not can_manage_org(current_user, db, new_parent):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限执行该移动操作",
        )

    try:
        move_organization(db, org, new_parent)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    db.commit()
    db.refresh(org)
    return org


@router.delete("/{org_id}", summary="删除组织")
def delete_org(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _context_tenant_id: str = Depends(require_context_tenant_id),
):
    """删除组织：仅空组织（无用户且无子组织）；根组织不可删"""
    org = get_org_or_404(db, org_id)

    if org.parent_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="根组织不可删除")
    if not can_manage_org(current_user, db, org):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权限操作该组织",
        )

    child_count = db.query(Organization).filter(Organization.parent_id == org.id).count()
    if child_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"组织下存在 {child_count} 个子组织，请先处理子组织",
        )
    user_count = db.query(User).filter(User.org_id == org.id).count()
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"组织下存在 {user_count} 个用户，请先迁移用户",
        )

    db.delete(org)
    db.commit()
    return {"message": f"已删除组织「{org.name}」"}