"""
文档级权限判定

可见性模型（上传时指定）：
- tenant ：租户内公开，本租户所有角色可见
- private：仅上传者可见
- roles  ：指定角色可见（allowed_roles 逗号分隔的多个角色编码）

管理员例外：admin 作为租户管理者，始终可见本租户全部文档。

设计要点：判定逻辑只有这一份实现，检索过滤（Chroma 元数据）与文档列表
（SQLAlchemy 模型）共用同一函数，避免两处规则不一致造成的越权漏洞。
"""

from typing import Callable, Dict, List, Optional

VALID_VISIBILITIES = ("tenant", "private", "roles")

# 可被指定为可见角色的编码（与平台内置角色一致）
ASSIGNABLE_ROLES = ("manager", "auditor", "employee")

VISIBILITY_LABELS = {
    "tenant": "租户内公开",
    "private": "仅上传者可见",
    "roles": "指定角色可见",
}

ADMIN_ROLE = "admin"


def normalize_roles(roles: Optional[str]) -> str:
    """规范化角色列表为逗号分隔串（去空、去重、保持顺序）"""
    if not roles:
        return ""
    seen: List[str] = []
    for raw in roles.replace("，", ",").split(","):
        code = raw.strip()
        if code and code not in seen:
            seen.append(code)
    return ",".join(seen)


def role_list(roles: Optional[str]) -> List[str]:
    """逗号分隔串 → 角色列表"""
    return [r for r in normalize_roles(roles).split(",") if r]


def validate_visibility(visibility: str, allowed_roles: Optional[str]) -> str:
    """
    校验可见性配置，返回规范化后的 allowed_roles。

    Raises:
        ValueError: 可见性取值非法，或 roles 模式下角色列表缺失/非法
    """
    if visibility not in VALID_VISIBILITIES:
        raise ValueError(
            f"可见性取值非法: {visibility}（可选 {'/'.join(VALID_VISIBILITIES)}）"
        )
    normalized = normalize_roles(allowed_roles)
    if visibility == "roles":
        if not normalized:
            raise ValueError("可见性为 roles 时必须指定 allowed_roles")
        invalid = [r for r in role_list(normalized) if r not in ASSIGNABLE_ROLES]
        if invalid:
            raise ValueError(
                f"无效的可见角色: {', '.join(invalid)}（可选 {'/'.join(ASSIGNABLE_ROLES)}）"
            )
    elif visibility != "roles":
        # 非 roles 模式忽略角色列表，避免残留配置误生效
        normalized = ""
    return normalized


def can_access(
    visibility: str,
    uploader_id: Optional[str],
    allowed_roles: Optional[str],
    user_id: str,
    role_code: str,
) -> bool:
    """
    判定某文档对指定用户是否可见。

    优先级：admin（租户管理者）> 上传者本人 > 可见性规则。
    上传者始终可见自己的文档，否则会出现"上传后自己都看不到"的反直觉情况
    （例如上传者角色不在 roles 允许列表中）。
    """
    if role_code == ADMIN_ROLE:
        return True
    if uploader_id and uploader_id == user_id:
        return True
    if visibility == "tenant":
        return True
    if visibility == "private":
        return False  # 仅上传者可见，此处已排除上传者本人
    if visibility == "roles":
        return role_code in role_list(allowed_roles)
    # 未知可见性按最严格处理（拒绝），避免配置错误导致越权
    return False


def make_chunk_filter(user_id: str, role_code: str) -> Callable[[Dict], bool]:
    """
    构造向量检索用的可见性谓词（作用于 Chroma 元数据字典）。

    元数据字段：visibility / uploader_id / allowed_roles（与文档表同名字段对应）
    """
    def _filter(meta: Dict) -> bool:
        return can_access(
            visibility=meta.get("visibility", "tenant"),
            uploader_id=meta.get("uploader_id"),
            allowed_roles=meta.get("allowed_roles"),
            user_id=user_id,
            role_code=role_code,
        )

    return _filter


def visibility_label(visibility: str) -> str:
    """可见性中文标签（前端展示用）"""
    return VISIBILITY_LABELS.get(visibility, visibility)
