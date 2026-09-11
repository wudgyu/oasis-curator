"""
RAG 问答 API 路由

- POST /api/qa/ask — 提交问题，走完整 RAG 管线（检索 → 重排序 → 生成）

权限：所有角色；租户隔离：检索范围限定 JWT 中的 tenant_id。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.doc_permission import make_chunk_filter
from app.core.permission import get_role_code
from app.core.rag_pipeline import rag_pipeline
from app.database import get_db
from app.models.user import User
from app.schemas.qa import QaAskRequest, QaAskResponse, RerankedChunkItem

router = APIRouter(prefix="/api/qa", tags=["RAG 问答"])


def _require_tenant(user: User) -> str:
    """问答必须归属具体租户，平台管理员（无租户）不允许调用"""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="平台管理员无租户归属，请使用租户账号提问",
        )
    return user.tenant_id


@router.post("/ask", response_model=QaAskResponse, summary="RAG 文档问答")
async def ask(
    req: QaAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """检索增强问答：回答附引用标注，文档中无答案时明确拒答"""
    tenant_id = _require_tenant(current_user)
    role_code = get_role_code(current_user, db)
    result = await rag_pipeline.answer(
        question=req.question,
        tenant_id=tenant_id,
        doc_id=req.doc_id,
        visibility_filter=make_chunk_filter(current_user.id, role_code),
    )
    return QaAskResponse(
        answer=result.answer,
        refused=result.refused,
        citations=result.citations,
        retrieved_count=result.retrieved_count,
        reranked=[
            RerankedChunkItem(
                score=c.score,
                reason=c.reason,
                text=c.chunk.text[:200],
                source_file=c.chunk.source_file,
                chunk_index=c.chunk.chunk_index,
                page=c.chunk.page,
            )
            for c in result.reranked
        ],
        provider=result.provider,
        model=result.model,
    )
