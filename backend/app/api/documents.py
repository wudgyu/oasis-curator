"""
文档管理 API 路由（RAG 入库 + 语义检索）

- POST   /api/documents           — 上传文档（解析 → 切分 → 向量化 → 入库）
- GET    /api/documents           — 分页列出当前租户文档
- DELETE /api/documents/{id}      — 删除文档（业务记录 + 向量 + 原文件）
- GET    /api/documents/search    — 语义检索（问题向量化 → Top-K，租户隔离）

权限：
- 上传/删除：admin / manager
- 检索/列表：所有角色
- 租户隔离：文档归属 JWT 中的 tenant_id，检索强制按租户过滤
"""

import asyncio
import math
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.chunker import chunk_document
from app.core.config import settings
from app.core.doc_parser import SUPPORTED_EXTENSIONS, parse_file
from app.core.embedder import embedder
from app.core.permission import get_role_code
from app.core.vector_store import vector_store
from app.database import get_db
from app.models.document import Document
from app.models.user import User
from app.schemas.document import (
    DocumentItem,
    DocumentListResponse,
    DocumentSearchResponse,
    DocumentUploadResponse,
    SearchChunkItem,
)

router = APIRouter(prefix="/api/documents", tags=["文档管理"])

_WRITE_ROLES = ("admin", "manager")


def _require_write(user: User, db: Session) -> None:
    """校验可写权限（admin / manager），否则 403"""
    if get_role_code(user, db) not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员和 manager 角色可管理文档",
        )


def _require_tenant(user: User) -> str:
    """文档必须归属具体租户，平台管理员（无租户）不允许操作"""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="平台管理员无租户归属，请使用租户账号管理文档",
        )
    return user.tenant_id


def _save_upload(file: UploadFile, doc_id: str, ext: str) -> Path:
    """落盘上传文件：{UPLOAD_DIR}/{doc_id}{ext}"""
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / f"{doc_id}{ext}"
    with dest.open("wb") as f:
        f.write(file.file.read())
    return dest


@router.post("", response_model=DocumentUploadResponse, summary="上传文档并向量化入库")
async def upload_document(
    file: UploadFile = File(..., description="PDF/TXT/Markdown 文档"),
    strategy: str = Form("paragraphs", description="切分策略：paragraphs / chars"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """上传 → 解析 → 切分 → Embedding → 向量入库，全程返回处理摘要"""
    _require_write(current_user, db)
    tenant_id = _require_tenant(current_user)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的文档格式: {ext}（支持 {sorted(SUPPORTED_EXTENSIONS)}）",
        )

    doc_id = str(uuid.uuid4())
    file_path = _save_upload(file, doc_id, ext)
    try:
        # 解析与切分为 CPU 密集/IO 操作，放线程池避免阻塞事件循环
        parsed = await asyncio.to_thread(parse_file, str(file_path))
        chunks = await asyncio.to_thread(chunk_document, parsed, strategy=strategy)
        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文档解析结果为空，无法入库",
            )
        # 引用溯源展示原始文件名（落盘文件名是 doc_id 命名）
        for c in chunks:
            c.source_file = file.filename or "unnamed"

        embeddings = await embedder.embed_texts([c.text for c in chunks])
        await asyncio.to_thread(
            vector_store.add_chunks, chunks, embeddings, doc_id, tenant_id
        )

        doc = Document(
            id=doc_id,
            tenant_id=tenant_id,
            file_name=file.filename or "unnamed",
            file_type=parsed.file_type,
            file_size=file_path.stat().st_size,
            chunk_count=len(chunks),
            chunk_strategy=strategy,
            uploader_id=current_user.id,
        )
        db.add(doc)
        db.commit()
        return DocumentUploadResponse(
            id=doc_id,
            file_name=doc.file_name,
            file_type=doc.file_type,
            char_count=parsed.char_count,
            page_count=parsed.page_count,
            chunk_count=len(chunks),
            chunk_strategy=strategy,
        )
    except HTTPException:
        raise
    except Exception as e:
        # 清理已写入的部分向量与落盘文件，避免脏数据
        try:
            await asyncio.to_thread(vector_store.delete_document, doc_id, tenant_id)
        except Exception:
            pass
        file_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文档处理失败: {e}",
        ) from e


@router.get("", response_model=DocumentListResponse, summary="分页列出当前租户文档")
def list_documents(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tenant_id = _require_tenant(current_user)
    total = (
        db.query(Document)
        .filter(Document.tenant_id == tenant_id)
        .count()
    )
    items = (
        db.query(Document)
        .filter(Document.tenant_id == tenant_id)
        .order_by(Document.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return DocumentListResponse(
        items=[
            DocumentItem(
                id=d.id,
                file_name=d.file_name,
                file_type=d.file_type,
                file_size=d.file_size,
                chunk_count=d.chunk_count,
                chunk_strategy=d.chunk_strategy,
                created_at=d.created_at,
            )
            for d in items
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.delete("/{doc_id}", summary="删除文档（记录 + 向量 + 原文件）")
async def delete_document(
    doc_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_write(current_user, db)
    tenant_id = _require_tenant(current_user)

    doc = (
        db.query(Document)
        .filter(Document.id == doc_id, Document.tenant_id == tenant_id)
        .first()
    )
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在")

    await asyncio.to_thread(vector_store.delete_document, doc_id, tenant_id)
    db.delete(doc)
    db.commit()

    # 清理原文件（不存在则忽略）
    for ext in SUPPORTED_EXTENSIONS:
        (Path(settings.UPLOAD_DIR) / f"{doc_id}{ext}").unlink(missing_ok=True)
    return {"id": doc_id, "deleted": True}


@router.get("/search", response_model=DocumentSearchResponse, summary="语义检索文本块")
async def search_documents(
    q: str = Query(..., min_length=1, description="检索问题"),
    top_k: int = Query(5, ge=1, le=20),
    doc_id: Optional[str] = Query(None, description="限定在指定文档内检索"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """问题向量化 → 向量检索 Top-K，强制按租户过滤"""
    tenant_id = _require_tenant(current_user)
    query_embedding = (await embedder.embed_texts([q]))[0]
    results = await asyncio.to_thread(
        vector_store.search, query_embedding, tenant_id, top_k, doc_id
    )
    return DocumentSearchResponse(
        query=q,
        chunks=[
            SearchChunkItem(
                text=r.text,
                score=r.score,
                source_file=r.source_file,
                chunk_index=r.chunk_index,
                page=r.page,
                doc_id=r.doc_id,
            )
            for r in results
        ],
    )
