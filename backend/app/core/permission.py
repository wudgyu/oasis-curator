"""
权限判定层（RBAC 数据范围统一收口）

角色 → 数据范围对照：
- admin:     全局（不限租户，上下文租户由 X-Tenant-Id 指定）
- manager:   本组织 + 所有子组织（物化路径前缀），可写
- auditor:   本组织 + 所有子组织（物化路径前缀），只读
- employee:  仅本组织（不含子组织），只读

写操作范围校验（manager）：目标组织 O 可写 ⟺ O.path 以 manager 所在组织 path 为前缀
（自身 path 是自身前缀，天然包含本组织）。

后续文档权限（RAG 阶段）直接复用本模块的 DataScope 原语。
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from sqlalchemy.orm import Session, Query

from app.models.user import User
from app.models.role import Role
from app.models.organization import Organization


class ScopeType(str, Enum):
    GLOBAL = "global"
    SUBTREE = "subtree"
    ORG_ONLY = "org_only"


@dataclass
class DataScope:
    """数据范围描述对象"""
    type: ScopeType
    # ORG_ONLY: 精确组织
    org_id: Optional[str] = None
    # SUBTREE: 组织树前缀
    path_prefix: Optional[str] = None

    @staticmethod
    def global_() -> "DataScope":
        return DataScope(type=ScopeType.GLOBAL)

    @staticmethod
    def subtree(path_prefix: str) -> "DataScope":
        return DataScope(type=ScopeType.SUBTREE, path_prefix=path_prefix)

    @staticmethod
    def org_only(org_id: str) -> "DataScope":
        return DataScope(type=ScopeType.ORG_ONLY, org_id=org_id)


def get_role_code(user: User, db: Session) -> str:
    """获取用户角色 code"""
    role = db.query(Role).filter(Role.id == user.role_id).first()
    return role.code if role else ""


def get_user_org(user: User, db: Session) -> Optional[Organization]:
    """获取用户所属组织（平台管理员为 None）"""
    if user.org_id is None:
        return None
    return db.query(Organization).filter(Organization.id == user.org_id).first()


def get_data_scope(user: User, db: Session) -> DataScope:
    """
    统一权限判定收口函数：返回当前用户的数据范围。

    所有列表查询（用户列表、后续文档查询）和写操作校验共用。
    """
    role_code = get_role_code(user, db)
    if role_code == "admin":
        return DataScope.global_()
    if role_code in ("manager", "auditor"):
        org = get_user_org(user, db)
        if org is None:
            # 数据异常：非 admin 用户必须有所属组织
            return DataScope.org_only("")
        return DataScope.subtree(path_prefix=org.path)
    # employee
    return DataScope.org_only(org_id=user.org_id or "")


def can_manage_org(user: User, db: Session, org: Organization) -> bool:
    """
    写操作范围校验：用户是否可管理指定组织。

    - admin: 任意组织
    - manager: org 位于其子树内（org.path 以其所属组织 path 为前缀）
    - auditor / employee: 否
    """
    role_code = get_role_code(user, db)
    if role_code == "admin":
        return True
    if role_code != "manager":
        return False
    my_org = get_user_org(user, db)
    if my_org is None:
        return False
    return org.path.startswith(my_org.path)


def can_manage_user(user: User, db: Session, target_user: User) -> bool:
    """写操作范围校验：用户是否可管理指定用户（通过目标用户所属组织判定）"""
    if target_user.org_id is None:
        # 平台管理员账号不受租户 manager 管辖
        return False
    target_org = db.query(Organization).filter(Organization.id == target_user.org_id).first()
    if target_org is None:
        return False
    return can_manage_org(user, db, target_org)


def build_child_path(parent_path: str, child_id: str) -> str:
    """生成子组织物化路径"""
    return f"{parent_path}{child_id}/"


def apply_scope_filter(query: Query, scope: DataScope, org_model) -> Query:
    """
    将数据范围应用到查询（组织维度过滤）。

    - GLOBAL:   不过滤（租户过滤由调用方负责）
    - SUBTREE:  join 组织表，path LIKE '{prefix}%'
    - ORG_ONLY: org_id = scope.org_id
    """
    if scope.type == ScopeType.GLOBAL:
        return query
    if scope.type == ScopeType.ORG_ONLY:
        return query.filter(org_model.id == scope.org_id)
    # SUBTREE
    if scope.path_prefix is None:
        return query.filter(False)  # 空范围
    return query.filter(org_model.path.like(f"{scope.path_prefix}%"))


def move_organization(
    db: Session, org: Organization, new_parent: Organization
) -> None:
    """
    移动组织到新的父组织，事务内重写子树物化路径。

    调用方负责 commit。校验规则：
    - 根组织（parent_id IS NULL）不可移动
    - 新父组织必须与被移动组织同租户
    - 新父组织不得位于被移动组织的子树内（防环）
    """
    if org.parent_id is None:
        raise ValueError("根组织不可移动")
    if new_parent.tenant_id != org.tenant_id:
        raise ValueError("不能移动到其他租户的组织下")
    if new_parent.path.startswith(org.path):
        raise ValueError("不能将组织移动到其子组织下（会形成环）")

    old_prefix = org.path
    new_prefix = build_child_path(new_parent.path, org.id)

    # 事务内重写整个子树的 path（含自身）
    descendants = (
        db.query(Organization)
        .filter(Organization.path.like(f"{old_prefix}%"))
        .all()
    )
    for d in descendants:
        d.path = new_prefix + d.path[len(old_prefix):]
    org.parent_id = new_parent.id