"""
文档上传/检索 请求与响应 Schema
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    """文档上传（解析 → 切分 → 向量化入库）结果"""

    id: str
    file_name: str
    file_type: str
    char_count: int = Field(description="解析出的总字符数")
    page_count: int = Field(default=0, description="页数（PDF）")
    chunk_count: int = Field(description="切分出的文本块数量")
    chunk_strategy: str = Field(description="使用的切分策略")


class DocumentItem(BaseModel):
    """文档列表单项"""

    id: str
    file_name: str
    file_type: str
    file_size: int
    chunk_count: int
    chunk_strategy: str
    created_at: datetime


class DocumentListResponse(BaseModel):
    """文档分页列表"""

    items: List[DocumentItem]
    total: int
    page: int
    page_size: int
    total_pages: int


class SearchChunkItem(BaseModel):
    """检索命中的文本块"""

    text: str
    score: float = Field(description="余弦相似度（0~1）")
    source_file: str
    chunk_index: int
    page: Optional[int] = None
    doc_id: str


class DocumentSearchResponse(BaseModel):
    """语义检索结果"""

    query: str
    chunks: List[SearchChunkItem]
