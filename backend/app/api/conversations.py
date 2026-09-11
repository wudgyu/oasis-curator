"""
问答会话 API 路由

- GET    /api/qa/conversations           — 会话列表（当前用户，按更新时间倒序）
- POST   /api/qa/conversations           — 新建会话
- GET    /api/qa/conversations/{id}      — 会话详情（含全部消息）
- PATCH  /api/qa/conversations/{id}      — 重命名会话
- DELETE /api/qa/conversations/{id}      — 删除会话及其消息

权限：会话为个人数据，仅归属用户本人可访问（admin 亦不可见他人会话）。
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.database import get_db
from app.models.conversation import ChatMessage, Conversation
from app.models.user import User
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationItem,
    MessageItem,
)

router = APIRouter(prefix="/api/qa/conversations", tags=["问答会话"])

DEFAULT_CONVERSATION_TITLE = "新会话"


def _get_own_conversation(db: Session, conversation_id: str, user: User) -> Conversation:
    """取当前用户的会话，不存在或非本人则 404（不泄漏他人会话是否存在）"""
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


def _message_to_item(msg: ChatMessage) -> MessageItem:
    return MessageItem(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        refused=msg.refused,
        citations=msg.citations or [],
        created_at=msg.created_at,
    )


@router.get("", response_model=list[ConversationItem], summary="会话列表")
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """按更新时间倒序返回当前用户的会话，附带消息条数"""
    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    if not conversations:
        return []

    # 一次分组查询取回各会话消息数，避免逐条 count 的 N+1
    ids = [c.id for c in conversations]
    counts = dict(
        db.query(ChatMessage.conversation_id, func.count(ChatMessage.id))
        .filter(ChatMessage.conversation_id.in_(ids))
        .group_by(ChatMessage.conversation_id)
        .all()
    )
    return [
        ConversationItem(
            id=c.id,
            title=c.title,
            message_count=counts.get(c.id, 0),
            created_at=c.created_at,
            updated_at=c.updated_at,
        )
        for c in conversations
    ]


@router.post("", response_model=ConversationItem, summary="新建会话")
def create_conversation(
    req: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="平台管理员无租户归属，请使用租户账号",
        )
    conv = Conversation(
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        title=req.title or DEFAULT_CONVERSATION_TITLE,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationItem(
        id=conv.id,
        title=conv.title,
        message_count=0,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.get("/{conversation_id}", response_model=ConversationDetail, summary="会话详情")
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = _get_own_conversation(db, conversation_id, current_user)
    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )
    return ConversationDetail(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[_message_to_item(m) for m in messages],
    )


@router.patch("/{conversation_id}", response_model=ConversationItem, summary="重命名会话")
def rename_conversation(
    conversation_id: str,
    req: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = _get_own_conversation(db, conversation_id, current_user)
    if not req.title:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="标题不能为空"
        )
    conv.title = req.title
    db.commit()
    db.refresh(conv)
    count = (
        db.query(func.count(ChatMessage.id))
        .filter(ChatMessage.conversation_id == conv.id)
        .scalar()
        or 0
    )
    return ConversationItem(
        id=conv.id,
        title=conv.title,
        message_count=count,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
    )


@router.delete("/{conversation_id}", summary="删除会话")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conv = _get_own_conversation(db, conversation_id, current_user)
    db.query(ChatMessage).filter(ChatMessage.conversation_id == conv.id).delete()
    db.delete(conv)
    db.commit()
    return {"id": conversation_id, "deleted": True}
