"""
RAG 问答 API 路由

- POST /api/qa/ask         — 提交问题，走完整 RAG 管线（检索 → 重排序 → 生成）
- POST /api/qa/ask/stream  — 同上，SSE 流式返回（meta / token / done 事件），
                             结果同时落库为会话历史（会话 CRUD 见 api/conversations.py）

权限：所有角色；租户隔离：检索范围限定 JWT 中的 tenant_id；
文档可见性：检索时应用 core/doc_permission 的过滤谓词。
"""

import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.doc_permission import make_chunk_filter
from app.core.permission import get_role_code
from app.core.rag_pipeline import rag_pipeline
from app.database import SessionLocal, get_db
from app.models.conversation import ChatMessage, Conversation
from app.models.user import User
from app.schemas.conversation import StreamAskRequest
from app.schemas.qa import QaAskRequest, QaAskResponse, RerankedChunkItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/qa", tags=["RAG 问答"])

DEFAULT_CONVERSATION_TITLE = "新会话"
TITLE_MAX_LEN = 30


def _require_tenant(user: User) -> str:
    """问答必须归属具体租户，平台管理员（无租户）不允许调用"""
    if not user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="平台管理员无租户归属，请使用租户账号提问",
        )
    return user.tenant_id


def _resolve_conversation(
    db: Session, conversation_id: str | None, user: User, tenant_id: str
) -> Conversation:
    """取指定会话（校验归属），conversation_id 为空则新建会话"""
    if conversation_id:
        conv = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.user_id == user.id)
            .first()
        )
        if conv is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在"
            )
        return conv

    conv = Conversation(tenant_id=tenant_id, user_id=user.id, title=DEFAULT_CONVERSATION_TITLE)
    db.add(conv)
    db.flush()
    return conv


def _sse(event: str, data: dict) -> str:
    """SSE 帧格式：event + JSON data（ensure_ascii=False 保证中文可读）"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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


@router.post("/ask/stream", summary="RAG 问答（SSE 流式，落库为会话历史）")
async def ask_stream(
    req: StreamAskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    流式问答：先返回检索与重排序结果（meta 事件），再逐 token 推送回答。

    会话处理：带 conversation_id 则续接该会话，否则新建会话；
    提问与回答均落库，用户可在会话列表中回看。
    """
    tenant_id = _require_tenant(current_user)
    role_code = get_role_code(current_user, db)
    user_id = current_user.id

    conversation = _resolve_conversation(db, req.conversation_id, current_user, tenant_id)
    conversation_id = conversation.id
    # 首个问题用作会话标题，便于在列表中辨识
    if conversation.title == DEFAULT_CONVERSATION_TITLE:
        conversation.title = req.question[:TITLE_MAX_LEN]

    db.add(
        ChatMessage(conversation_id=conversation_id, role="user", content=req.question)
    )
    db.commit()

    async def event_stream() -> AsyncGenerator[str, None]:
        answer_text = ""
        refused = False
        citations: list[str] = []
        sources: list[dict] = []
        parts: list[str] = []
        try:
            async for event in rag_pipeline.answer_stream(
                question=req.question,
                tenant_id=tenant_id,
                doc_id=req.doc_id,
                visibility_filter=make_chunk_filter(user_id, role_code),
            ):
                if event["type"] == "meta":
                    # 候选块随消息落库，供历史消息点击引用时展示原文
                    sources = event["reranked"]
                    yield _sse(
                        "meta",
                        {
                            "conversation_id": conversation_id,
                            "retrieved_count": event["retrieved_count"],
                            "reranked": event["reranked"],
                        },
                    )
                elif event["type"] == "token":
                    parts.append(event["text"])
                    yield _sse("token", {"text": event["text"]})
                elif event["type"] == "done":
                    answer_text = event["answer"]
                    refused = event["refused"]
                    citations = event["citations"]
                    yield _sse(
                        "done",
                        {
                            "answer": answer_text,
                            "refused": refused,
                            "citations": citations,
                            "provider": event["provider"],
                            "model": event["model"],
                        },
                    )
        except Exception as e:  # noqa: BLE001  流式过程中出错需通知前端而非断流
            logger.exception("流式问答失败")
            yield _sse("error", {"message": f"生成失败: {e}"})
        finally:
            # 客户端中途断开时保留已生成的部分内容；完全未生成则不落库
            # （用独立会话写库：请求级会话在流式响应期间的生命周期不可靠）
            final_text = answer_text or "".join(parts)
            if final_text.strip():
                with SessionLocal() as write_db:
                    write_db.add(
                        ChatMessage(
                            conversation_id=conversation_id,
                            role="assistant",
                            content=final_text,
                            refused=refused,
                            citations=citations,
                            sources=sources,
                        )
                    )
                    conv = (
                        write_db.query(Conversation)
                        .filter(Conversation.id == conversation_id)
                        .first()
                    )
                    if conv is not None:
                        conv.updated_at = func.now()  # type: ignore[assignment]
                    write_db.commit()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 关闭反向代理缓冲，保证逐字下发
        },
    )
