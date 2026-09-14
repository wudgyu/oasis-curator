"""
文档处理 Agent API 路由

- POST /api/agent/run          — 同步执行，返回完整执行轨迹
- POST /api/agent/run/stream   — SSE 流式执行，逐步推送工具调用与最终答复

权限：admin / manager（Agent 会写入知识库，与文档上传保持同一权限口径）。
租户隔离：文档检索与入库均限定 JWT 中的 tenant_id。
"""

import logging
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.agent_tools import AgentContext
from app.core.config import settings
from app.core.doc_agent import MODE_AUTO, DocumentAgent
from app.core.doc_parser import FILE_TYPE_EXTENSIONS
from app.core.doc_permission import validate_visibility
from app.core.permission import get_role_code
from app.database import get_db
from app.models.document import Document
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["文档处理 Agent"])

_WRITE_ROLES = ("admin", "manager")
_agent = DocumentAgent()


class AgentRunRequest(BaseModel):
    """Agent 执行请求"""

    instruction: str = Field(
        min_length=2, max_length=500, description="自然语言处理需求"
    )
    doc_id: Optional[str] = Field(
        default=None, description="待处理文档 ID（来自文档列表），缺省则仅按指令执行"
    )
    visibility: str = Field(default="tenant", description="入库产物的可见性")
    allowed_roles: Optional[str] = Field(default=None, description="visibility=roles 时的角色")
    provider: Optional[str] = Field(default=None, description="指定 LLM provider")
    mode: str = Field(default=MODE_AUTO, description="native / prompt / auto")


def _require_write(user: User, db: Session) -> None:
    if get_role_code(user, db) not in _WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员和 manager 角色可执行文档处理 Agent",
        )


def _build_context(req: AgentRunRequest, user: User, db: Session) -> AgentContext:
    """组装执行上下文：定位待处理文档文件"""
    file_path: Optional[str] = None
    file_name: Optional[str] = None

    if req.doc_id:
        doc = (
            db.query(Document)
            .filter(Document.id == req.doc_id, Document.tenant_id == user.tenant_id)
            .first()
        )
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="文档不存在"
            )
        file_name = doc.file_name
        # 上传文档落盘为 {doc_id}{ext}；Agent 自身产出的文档（file_type=agent）无原始文件
        for ext in FILE_TYPE_EXTENSIONS.get(doc.file_type, ()):
            candidate = Path(settings.UPLOAD_DIR) / f"{doc.id}{ext}"
            if candidate.exists():
                file_path = str(candidate)
                break

    # 入库产物的可见性沿用上传口径（不指定时为租户内公开）
    try:
        normalized_roles = validate_visibility(req.visibility, req.allowed_roles)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    return AgentContext(
        tenant_id=user.tenant_id or "",
        user_id=user.id,
        file_path=file_path,
        file_name=file_name,
        visibility=req.visibility,
        allowed_roles=normalized_roles,
    )


@router.post("/run", summary="执行文档处理 Agent（同步返回完整轨迹）")
async def run_agent(
    req: AgentRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """LLM 自主编排工具完成文档处理需求，返回每一步的工具调用与最终答复"""
    _require_write(current_user, db)
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="平台管理员无租户归属，请使用租户账号执行",
        )

    ctx = _build_context(req, current_user, db)
    run = await _agent.run(req.instruction, ctx, provider=req.provider, mode=req.mode)
    return run.to_dict()


@router.post("/run/stream", summary="执行文档处理 Agent（SSE 流式推送执行过程）")
async def run_agent_stream(
    req: AgentRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    流式执行：每完成一次工具调用推送一个 step 事件，最后推送 done 事件。

    前端据此展示 Agent 的执行过程（调用哪个工具、参数、结果、耗时），
    而非黑盒等待最终答案。
    """
    _require_write(current_user, db)
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="平台管理员无租户归属，请使用租户账号执行",
        )

    ctx = _build_context(req, current_user, db)

    async def event_stream() -> AsyncGenerator[str, None]:
        import json

        try:
            async for event in _agent.run_stream(
                req.instruction, ctx, provider=req.provider, mode=req.mode
            ):
                yield f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001  流式过程中出错需通知前端
            logger.exception("Agent 流式执行失败")
            yield f"event: error\ndata: {json.dumps({'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
