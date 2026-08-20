"""
IAM 配置生成器（自然语言 → 权限配置 JSON）

基于 Prompt Engineering 将自然语言权限需求转换为符合 RBAC 2.0 模型的
结构化 JSON 配置，结合 Schema 校验与自动重试纠错。

面试核心案例：将 11 年 IAM 经验 AI 化。
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from app.core.llm_provider import LLMProvider, llm_provider

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic 输出 Schema
# ---------------------------------------------------------------------------


class PermissionItem(BaseModel):
    """单条权限：资源 + 操作列表"""

    resource: str = Field(description="资源类型，如 ecs, rds, oss, vpc")
    actions: List[str] = Field(description="操作列表，如 ['read', 'list', 'create', 'delete']")


class DataScope(BaseModel):
    """数据范围：限制角色可访问的数据边界"""

    type: str = Field(description="数据范围类型：global / by_location / by_org / by_department")
    locations: Optional[List[str]] = Field(default=None, description="可访问的机房/地域列表")
    orgs: Optional[List[str]] = Field(default=None, description="可访问的组织列表")
    departments: Optional[List[str]] = Field(default=None, description="可访问的部门列表")


class RoleDefinition(BaseModel):
    """角色定义"""

    name: str = Field(description="角色名称（中文）")
    code: str = Field(description="角色编码，小写字母 + 下划线，如 bj_sh_readonly")
    description: str = Field(description="角色描述，说明该角色的权限范围")


class IamRoleConfig(BaseModel):
    """IAM 角色完整配置（自然语言生成的目标输出）"""

    role: RoleDefinition
    permissions: List[PermissionItem] = Field(min_length=1)
    data_scope: DataScope


# ---------------------------------------------------------------------------
# 预设模板
# ---------------------------------------------------------------------------

# 模板定义：keyword → 模板描述（注入 Prompt 作为上下文）
PRESET_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "全局只读": {
        "keywords": ["全局只读", "只读", "readonly", "read only", "查看所有"],
        "description": "全局只读角色：可查看所有资源但无修改权限",
        "example": {
            "role": {
                "name": "全局只读",
                "code": "global_readonly",
                "description": "对所有资源具有只读权限",
            },
            "permissions": [
                {"resource": "ecs", "actions": ["read", "list"]},
                {"resource": "rds", "actions": ["read", "list"]},
                {"resource": "oss", "actions": ["read", "list"]},
                {"resource": "vpc", "actions": ["read", "list"]},
            ],
            "data_scope": {"type": "global"},
        },
    },
    "部门管理员": {
        "keywords": ["部门管理员", "部门管理", "部门admin", "department admin"],
        "description": "部门管理员角色：可管理本部门所有资源",
        "example": {
            "role": {
                "name": "部门管理员",
                "code": "dept_admin",
                "description": "管理本部门的所有云资源",
            },
            "permissions": [
                {"resource": "ecs", "actions": ["read", "list", "create", "delete", "update"]},
                {"resource": "rds", "actions": ["read", "list", "create", "delete", "update"]},
                {"resource": "oss", "actions": ["read", "list", "create", "delete", "update"]},
            ],
            "data_scope": {"type": "by_department"},
        },
    },
    "审计员": {
        "keywords": ["审计员", "审计", "auditor", "audit", "合规"],
        "description": "审计员角色：可查看所有操作日志和资源，不可修改",
        "example": {
            "role": {
                "name": "审计员",
                "code": "auditor",
                "description": "审计所有资源的操作日志与配置",
            },
            "permissions": [
                {"resource": "ecs", "actions": ["read", "list"]},
                {"resource": "rds", "actions": ["read", "list"]},
                {"resource": "oss", "actions": ["read", "list"]},
                {"resource": "vpc", "actions": ["read", "list"]},
                {"resource": "audit_log", "actions": ["read", "list", "export"]},
            ],
            "data_scope": {"type": "global"},
        },
    },
    "项目管理员": {
        "keywords": ["项目管理员", "项目admin", "project admin"],
        "description": "项目管理员角色：可管理项目范围内的资源",
        "example": {
            "role": {
                "name": "项目管理员",
                "code": "project_admin",
                "description": "管理项目范围内的云资源",
            },
            "permissions": [
                {"resource": "ecs", "actions": ["read", "list", "create", "delete", "update"]},
                {"resource": "rds", "actions": ["read", "list", "create", "delete", "update"]},
                {"resource": "oss", "actions": ["read", "list", "create", "delete"]},
                {"resource": "vpc", "actions": ["read", "list"]},
            ],
            "data_scope": {"type": "by_org"},
        },
    },
}

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一个 IAM（身份与访问管理）权限配置专家。你熟悉 RBAC 2.0 权限模型，
能够将用户的自然语言需求转换为结构化的权限配置 JSON。

## 输出格式规范

你必须输出一个合法的 JSON 对象，结构如下：

```json
{
  "role": {
    "name": "角色名称（中文）",
    "code": "角色编码（小写字母+下划线，如 dept_admin）",
    "description": "角色描述"
  },
  "permissions": [
    {"resource": "资源类型", "actions": ["操作1", "操作2"]}
  ],
  "data_scope": {
    "type": "global | by_location | by_org | by_department",
    "locations": ["地域列表，仅 by_location 时填写"],
    "orgs": ["组织列表，仅 by_org 时填写"],
    "departments": ["部门列表，仅 by_department 时填写"]
  }
}
```

## 资源类型参考

- ecs: 云主机
- rds: 云数据库
- oss: 对象存储
- vpc: 私有网络
- ecs_snapshot: 云主机快照
- rds_backup: 数据库备份
- audit_log: 审计日志
- iam: 权限管理

## 操作类型参考

- read: 查看详情
- list: 查看列表
- create: 创建
- update: 修改配置
- delete: 删除
- export: 导出

## 数据范围类型

- global: 全局，所有数据
- by_location: 按地域/机房限制
- by_org: 按组织限制
- by_department: 按部门限制

## 重要规则

1. 只输出 JSON，不要包含任何额外的解释或 markdown 标记
2. role.code 必须是小写字母 + 下划线，不能包含中文或特殊字符
3. permissions 至少包含 1 条
4. data_scope.type 必须与 locations/orgs/departments 字段对应
5. 如果用户没有明确指定数据范围，默认使用 global
6. 根据用户描述的操作意图推断 actions（如"只能看"→ read, list；"管理"→ 全部 CRUD）

## 示例

用户输入：创建一个只读角色，只能看北京机房和上海机房的云主机资源

输出：
{
  "role": {
    "name": "北京上海机房只读",
    "code": "bj_sh_readonly",
    "description": "只能查看北京和上海机房的云主机资源"
  },
  "permissions": [
    {"resource": "ecs", "actions": ["read", "list"]},
    {"resource": "ecs_snapshot", "actions": ["read", "list"]}
  ],
  "data_scope": {
    "type": "by_location",
    "locations": ["beijing", "shanghai"]
  }
}

用户输入：创建一个数据库管理员，可以管理杭州机房的所有数据库

输出：
{
  "role": {
    "name": "杭州数据库管理员",
    "code": "hz_dba",
    "description": "管理杭州机房的所有数据库资源"
  },
  "permissions": [
    {"resource": "rds", "actions": ["read", "list", "create", "update", "delete"]},
    {"resource": "rds_backup", "actions": ["read", "list", "create", "delete"]}
  ],
  "data_scope": {
    "type": "by_location",
    "locations": ["hangzhou"]
  }
}"""

# ---------------------------------------------------------------------------
# 模板匹配
# ---------------------------------------------------------------------------


def _match_template(user_input: str) -> Optional[Dict[str, Any]]:
    """根据用户输入的关键词匹配预设模板"""
    text = user_input.lower()
    for template_name, template_def in PRESET_TEMPLATES.items():
        for keyword in template_def["keywords"]:
            if keyword.lower() in text:
                logger.info("匹配到预设模板: %s (关键词: %s)", template_name, keyword)
                return template_def
    return None


# ---------------------------------------------------------------------------
# JSON 提取与清洗
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> str:
    """
    从 LLM 输出中提取 JSON 字符串。

    处理 LLM 可能返回的 markdown 代码块、前后空白、尾随逗号等问题。
    """
    # 尝试从 markdown 代码块中提取
    code_block_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if code_block_match:
        text = code_block_match.group(1)

    # 找到第一个 { 和最后一个 } 之间的内容
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        text = text[start : end + 1]

    # 移除尾随逗号（JSON 标准不允许）
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)

    return text.strip()


# ---------------------------------------------------------------------------
# 核心生成逻辑
# ---------------------------------------------------------------------------


class IamConfigGenerator:
    """
    IAM 配置生成器

    将自然语言权限需求 → LLM 生成 → Pydantic 校验 → 重试修复 → 最终输出
    """

    MAX_RETRIES = 2  # Schema 校验失败后的最大重试次数

    def __init__(self, llm: Optional[LLMProvider] = None) -> None:
        self._llm = llm or llm_provider

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    async def generate(
        self,
        user_input: str,
        tenant_id: Optional[str] = None,
        existing_role_codes: Optional[List[str]] = None,
    ) -> Tuple[IamRoleConfig, Dict[str, Any]]:
        """
        生成 IAM 角色配置。

        Args:
            user_input: 用户自然语言输入
            tenant_id: 租户 ID（用于命名空间隔离）
            existing_role_codes: 当前租户已存在的角色编码列表（用于冲突检测）

        Returns:
            (IamRoleConfig, metadata) 元组
            metadata 包含:
                - template_matched: 是否匹配了预设模板
                - template_name: 匹配到的模板名
                - retries: 重试次数
                - conflicts: 冲突的角色编码列表
        """
        metadata: Dict[str, Any] = {
            "template_matched": False,
            "template_name": None,
            "retries": 0,
            "conflicts": [],
        }

        # 1. 模板匹配
        template = _match_template(user_input)
        if template:
            metadata["template_matched"] = True
            metadata["template_name"] = template.get("description", "")

        # 2. 构建消息
        messages = self._build_messages(user_input, template)

        # 3. LLM 生成 + Schema 校验 + 重试
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                response = await self._llm.chat(
                    messages=messages,
                    temperature=0.3,  # 低温度，提高结构化输出稳定性
                )
                config = self._parse_and_validate(response.content)
                metadata["retries"] = attempt

                # 4. 冲突检测
                if existing_role_codes and config.role.code in existing_role_codes:
                    metadata["conflicts"] = [config.role.code]

                return config, metadata

            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(
                    "IAM 配置生成第 %d/%d 次校验失败: %s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    e,
                )
                if attempt < self.MAX_RETRIES:
                    # 追加错误反馈，让 LLM 修复
                    messages.append({
                        "role": "assistant",
                        "content": response.content if "response" in dir() else "",
                    })
                    messages.append({
                        "role": "user",
                        "content": (
                            f"你的输出不符合要求的 JSON Schema。错误信息：{e}\n"
                            "请严格按照 Schema 要求重新输出完整的 JSON，不要包含任何额外文字。"
                        ),
                    })
                else:
                    raise ValueError(
                        f"IAM 配置生成失败：{self.MAX_RETRIES} 次重试后仍无法生成合法配置。"
                        f"最后错误: {e}"
                    ) from e

        # 不应该到达这里
        raise RuntimeError("IAM 配置生成异常退出")

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        user_input: str,
        template: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """构建 LLM 对话消息"""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
        ]

        # 如果匹配到模板，注入模板上下文
        if template:
            template_example = json.dumps(template["example"], ensure_ascii=False, indent=2)
            messages.append({
                "role": "user",
                "content": (
                    f"用户可能想要一个类似以下模板的权限配置：\n"
                    f"模板描述：{template['description']}\n"
                    f"模板示例：{template_example}\n\n"
                    f"请根据以下用户的具体需求，在模板基础上调整生成最终配置。"
                ),
            })
            messages.append({
                "role": "assistant",
                "content": "好的，我会参考模板并根据用户具体需求调整。",
            })

        messages.append({
            "role": "user",
            "content": f"请为以下需求生成 IAM 角色配置：{user_input}",
        })

        return messages

    def _parse_and_validate(self, raw_text: str) -> IamRoleConfig:
        """解析 JSON 文本并校验 Schema"""
        json_str = _extract_json(raw_text)
        data = json.loads(json_str)
        return IamRoleConfig(**data)

    # ------------------------------------------------------------------
    # 模板查询 API
    # ------------------------------------------------------------------

    @classmethod
    def list_templates(cls) -> List[Dict[str, Any]]:
        """列出所有预设模板"""
        return [
            {
                "name": name,
                "description": tpl["description"],
                "keywords": tpl["keywords"],
            }
            for name, tpl in PRESET_TEMPLATES.items()
        ]

    @classmethod
    def match_template_name(cls, user_input: str) -> Optional[str]:
        """匹配用户输入对应的模板名称（用于前端展示）"""
        template = _match_template(user_input)
        return template["description"] if template else None


# ---------------------------------------------------------------------------
# 模块级便捷实例
# ---------------------------------------------------------------------------

iam_generator = IamConfigGenerator()