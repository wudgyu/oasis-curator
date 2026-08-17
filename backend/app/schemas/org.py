"""
组织相关 Pydantic 模型
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class OrgCreate(BaseModel):
    """创建组织请求"""
    name: str = Field(..., min_length=1, max_length=100, description="组织名称")
    parent_id: str = Field(..., description="父组织 ID")


class OrgUpdate(BaseModel):
    """重命名组织请求"""
    name: str = Field(..., min_length=1, max_length=100, description="组织名称")


class OrgMoveRequest(BaseModel):
    """移动组织请求"""
    new_parent_id: str = Field(..., description="新父组织 ID")


class OrgResponse(BaseModel):
    """组织详情"""
    id: str
    name: str
    path: str
    parent_id: Optional[str] = None
    tenant_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OrgTreeNode(BaseModel):
    """组织树节点（嵌套结构）"""
    id: str
    name: str
    path: str
    parent_id: Optional[str] = None
    user_count: int = 0
    children: List["OrgTreeNode"] = []


OrgTreeNode.model_rebuild()