"""
IAM 配置生成器请求/响应 Schema
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class IamGenerateRequest(BaseModel):
    """自然语言权限需求请求"""

    requirement: str = Field(
        min_length=2,
        max_length=500,
        description="自然语言权限需求描述，如 '创建一个只读角色，只能看北京机房的云主机'",
    )


class IamTemplateInfo(BaseModel):
    """预设模板信息"""

    name: str
    description: str
    keywords: List[str]


class IamGenerateResponse(BaseModel):
    """生成结果响应"""

    config: dict = Field(description="生成的 IAM 角色配置 JSON")
    template_matched: bool = Field(description="是否匹配了预设模板")
    template_name: Optional[str] = Field(default=None, description="匹配到的模板名称")
    retries: int = Field(description="Schema 校验重试次数")
    conflicts: List[str] = Field(
        default_factory=list, description="与已有角色冲突的编码列表"
    )
