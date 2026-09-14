"""
文档处理 Agent 的工具集

设计要点：
- 工具定义与执行分离：`@tool` 装饰器登记 JSON Schema 与处理函数，
  新增工具 = 一个函数 + 一段 Schema（agent 侧无需改动）
- 工具通过 AgentContext 共享数据：解析结果、当前工作文本、入库产物都挂在
  上下文上，因此 LLM 只需决定「调用哪些工具、按什么顺序」，
  不必把大段文本回填到参数里（否则易截断且浪费 token）
- 文本类参数可省略：省略时自动取上下文中的当前工作文本
  （如 translate_text 省略 text 即翻译当前文档内容）
- 文件访问限制在受控目录（上传目录）内，避免 LLM 指定任意路径读取主机文件
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.core.chunker import chunk_by_paragraphs
from app.core.config import settings
from app.core.doc_parser import parse_file
from app.core.embedder import embedder
from app.core.llm_provider import LLMProvider, llm_provider
from app.core.vector_store import vector_store

logger = logging.getLogger(__name__)

# 传给 LLM 的文本上限（约数千 token），超出部分截断并提示
MAX_LLM_INPUT_CHARS = 6000


# ---------------------------------------------------------------------------
# 执行上下文
# ---------------------------------------------------------------------------


@dataclass
class AgentContext:
    """一次 Agent 运行的可变状态（工具间共享）"""

    tenant_id: str
    user_id: str
    file_path: Optional[str] = None  # 待处理文档的落盘路径
    file_name: Optional[str] = None
    visibility: str = "tenant"
    allowed_roles: str = ""
    llm: LLMProvider = field(default_factory=lambda: llm_provider)

    # 工具产物
    parsed_text: str = ""  # parse_document 的全文
    working_text: str = ""  # 当前工作文本（翻译/摘要的输入输出）
    tables: List[Dict[str, Any]] = field(default_factory=list)  # [{page, markdown}]
    document_id: Optional[str] = None  # index_chunks 入库后生成的文档 ID
    indexed_chunks: int = 0

    def resolved_path(self, file_path: Optional[str]) -> Path:
        """
        解析待处理文件路径：缺省用上下文文档；显式路径必须落在上传目录内。

        Raises:
            ValueError: 未提供文档，或路径越界
        """
        if not file_path:
            if not self.file_path:
                raise ValueError("未提供待处理文档，请先上传文档或指定上传目录内的文件")
            return Path(self.file_path)

        candidate = Path(file_path)
        # 与当前文档同名（模型常按上下文里的文件名回传）：直接沿用上下文路径，
        # 避免因文件不在上传目录而报"文件不存在"的无谓失败
        if self.file_path and self.file_name and candidate.name == self.file_name:
            return Path(self.file_path)

        upload_dir = Path(settings.UPLOAD_DIR).resolve()
        # 只接受纯文件名：拒绝绝对路径、目录层级与 .. 穿越
        if candidate.is_absolute() or candidate.name != str(candidate) or ".." in candidate.parts:
            raise ValueError(
                f"文件路径越界（仅允许访问上传目录内的文件，请只传文件名）: {file_path}"
            )
        target = (upload_dir / candidate.name).resolve()
        if not str(target).startswith(str(upload_dir)):
            raise ValueError(f"文件路径越界（仅允许访问上传目录内的文件）: {file_path}")
        if not target.exists():
            raise ValueError(f"文件不存在: {file_path}")
        return target

    def current_text(self, text: Optional[str]) -> str:
        """取当前工作文本：显式传入优先，其次解析结果"""
        if text:
            return text
        return self.working_text or self.parsed_text


# ---------------------------------------------------------------------------
# 工具注册表
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    """工具定义：名称 + 描述 + JSON Schema + 执行函数"""

    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema
    handler: Callable  # async (ctx, **kwargs) -> dict


TOOL_REGISTRY: Dict[str, ToolSpec] = {}


def tool(name: str, description: str, parameters: Dict[str, Any]):
    """装饰器：登记一个工具（新增工具只需函数 + Schema）"""

    def decorator(fn: Callable):
        TOOL_REGISTRY[name] = ToolSpec(
            name=name, description=description, parameters=parameters, handler=fn
        )
        return fn

    return decorator


def get_tool_schemas() -> List[Dict[str, Any]]:
    """OpenAI 兼容的 tools 参数格式"""
    return [
        {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }
        for spec in TOOL_REGISTRY.values()
    ]


def describe_tools() -> str:
    """工具清单的文本描述（Prompt 注入降级模式使用）"""
    lines = []
    for spec in TOOL_REGISTRY.values():
        params = spec.parameters.get("properties", {})
        required = set(spec.parameters.get("required", []))
        param_desc = "、".join(
            f"{name}({'必填' if name in required else '可选'}: {meta.get('description', '')})"
            for name, meta in params.items()
        )
        lines.append(f"- {spec.name}: {spec.description}\n  参数: {param_desc or '无'}")
    return "\n".join(lines)


async def execute_tool(ctx: AgentContext, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """
    执行工具并统一错误处理。

    Returns:
        {"ok": bool, "tool": name, ...} —— 失败时含 error 字段，
        供 LLM 判断后给出替代方案
    """
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return {
            "ok": False,
            "tool": name,
            "error": f"未知工具 {name}，可用工具: {', '.join(TOOL_REGISTRY)}",
        }
    try:
        result = await spec.handler(ctx, **(args or {}))
        return {"ok": True, "tool": name, **(result or {})}
    except TypeError as e:
        return {"ok": False, "tool": name, "error": f"参数不合法: {e}"}
    except Exception as e:  # noqa: BLE001  工具失败需回传 LLM 而非中断整条链路
        logger.warning("工具 %s 执行失败: %s", name, e)
        return {"ok": False, "tool": name, "error": str(e)}


# ---------------------------------------------------------------------------
# 工具实现
# ---------------------------------------------------------------------------


@tool(
    name="parse_document",
    description="解析文档，提取纯文本与表格（支持 PDF / Word / TXT / Markdown）。"
    "解析结果会作为后续工具的默认输入。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "上传目录内的文件名，缺省使用当前上传的文档",
            },
            "file_type": {"type": "string", "description": "文档类型，可省略（按扩展名自动判断）"},
        },
        "required": [],
    },
)
async def parse_document(
    ctx: AgentContext, file_path: Optional[str] = None, file_type: Optional[str] = None
) -> Dict[str, Any]:
    """解析文档，产物写入 ctx.parsed_text / ctx.tables"""
    path = ctx.resolved_path(file_path)
    parsed = parse_file(path)

    ctx.parsed_text = parsed.text
    ctx.working_text = parsed.text
    ctx.file_name = ctx.file_name or parsed.file_name
    ctx.tables = _collect_tables(parsed)

    return {
        "file_name": parsed.file_name,
        "file_type": parsed.file_type,
        "char_count": parsed.char_count,
        "page_count": parsed.page_count,
        "table_count": parsed.table_count,
        "preview": parsed.text[:300],
    }


@tool(
    name="extract_tables",
    description="提取文档中的表格数据（Markdown 格式），可按页码范围筛选。"
    "表格内容如已在解析结果中，可直接使用。",
    parameters={
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "上传目录内的文件名，可省略"},
            "page_range": {
                "type": "string",
                "description": "页码范围，如 '1-3' 或 '2'；省略表示全部页面",
            },
        },
        "required": [],
    },
)
async def extract_tables(
    ctx: AgentContext, file_path: Optional[str] = None, page_range: Optional[str] = None
) -> Dict[str, Any]:
    """提取表格（复用解析阶段结果，未解析则先解析）"""
    if not ctx.tables:
        await parse_document(ctx, file_path=file_path)

    pages = _parse_page_range(page_range)
    tables = [t for t in ctx.tables if pages is None or t["page"] in pages]
    if not tables:
        return {
            "table_count": 0,
            "message": f"未找到表格（页码筛选: {page_range or '全部'}）",
            "tables": [],
        }
    return {
        "table_count": len(tables),
        "tables": [
            {"page": t["page"], "markdown": t["markdown"], "rows": t["rows"]}
            for t in tables
        ],
    }


@tool(
    name="translate_text",
    description="翻译文本（中英互译等）。省略 text 时翻译当前文档内容。"
    "翻译结果会成为后续工具的默认输入。",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "待翻译文本，省略则翻译当前文档内容"},
            "target_lang": {
                "type": "string",
                "description": "目标语言，如 中文 / 英文 / 日文",
            },
        },
        "required": ["target_lang"],
    },
)
async def translate_text(
    ctx: AgentContext, target_lang: str, text: Optional[str] = None
) -> Dict[str, Any]:
    """LLM 翻译，产物写入 ctx.working_text"""
    source = await _ensure_source_text(ctx, text)

    for_llm, truncated = _truncate(source)
    response = await ctx.llm.chat(
        [
            {
                "role": "system",
                "content": f"你是专业翻译。将用户提供的文本翻译为{target_lang}，"
                f"只输出译文，不要解释、不要添加原文。",
            },
            {"role": "user", "content": for_llm},
        ],
        temperature=1.0,
        max_tokens=settings.LLM_MAX_TOKENS,
    )
    translated = (response.content or "").strip()
    if not translated:
        raise ValueError("翻译服务未返回内容，请稍后重试")

    ctx.working_text = translated
    return {
        "target_lang": target_lang,
        "char_count": len(translated),
        "truncated": truncated,
        "preview": translated[:300],
    }


@tool(
    name="summarize_text",
    description="对文本生成摘要。省略 text 时对当前文档内容做摘要。",
    parameters={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "待摘要文本，省略则使用当前文档内容"},
            "max_length": {
                "type": "integer",
                "description": "摘要字数上限，默认 200",
            },
        },
        "required": [],
    },
)
async def summarize_text(
    ctx: AgentContext, max_length: int = 200, text: Optional[str] = None
) -> Dict[str, Any]:
    """LLM 摘要，产物写入 ctx.summary"""
    source = await _ensure_source_text(ctx, text)

    for_llm, truncated = _truncate(source)
    response = await ctx.llm.chat(
        [
            {
                "role": "system",
                "content": f"你是文档摘要助手。用不超过 {max_length} 字概括用户提供的文档内容，"
                f"只输出摘要正文，不要解释。",
            },
            {"role": "user", "content": for_llm},
        ],
        temperature=1.0,
        max_tokens=1000,
    )
    summary = (response.content or "").strip()
    if not summary:
        raise ValueError("摘要服务未返回内容，请稍后重试")

    ctx.summary = summary
    return {"max_length": max_length, "char_count": len(summary), "summary": summary, "truncated": truncated}


@tool(
    name="index_chunks",
    description="将文本切分、向量化后入库，供后续检索问答。省略 chunks 时对当前文档内容切分入库。",
    parameters={
        "type": "object",
        "properties": {
            "chunks": {
                "type": "array",
                "items": {"type": "string"},
                "description": "待入库的文本块列表，省略则自动切分当前文档内容",
            },
            "metadata": {
                "type": "object",
                "description": "附加元数据（如标题、来源说明），会随向量一并保存",
            },
        },
        "required": [],
    },
)
async def index_chunks(
    ctx: AgentContext,
    chunks: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """切分 → 向量化 → 写入向量库，并登记文档记录"""
    texts = [c.strip() for c in (chunks or []) if c and c.strip()]
    if not texts:
        texts = chunk_by_paragraphs(await _ensure_source_text(ctx, None))

    if not texts:
        raise ValueError("切分结果为空，无法入库")

    doc_id = ctx.document_id or _new_id()
    # 与文档上传接口保持一致：可见性写入向量元数据，检索时据此过滤
    embeddings = await embedder.embed_texts(texts)
    from app.core.chunker import Chunk  # 局部导入避免与 chunker 循环依赖

    chunk_objs = [
        Chunk(
            text=text,
            source_file=ctx.file_name or "agent_output",
            chunk_index=i,
            strategy="paragraphs",
        )
        for i, text in enumerate(texts)
    ]
    vector_store.add_chunks(
        chunk_objs,
        embeddings,
        doc_id,
        ctx.tenant_id,
        ctx.visibility,
        ctx.user_id,
        ctx.allowed_roles,
    )
    _register_document(ctx, doc_id, texts, metadata)

    ctx.document_id = doc_id
    ctx.indexed_chunks = len(texts)
    return {
        "document_id": doc_id,
        "chunk_count": len(texts),
        "file_name": ctx.file_name,
        "metadata": metadata or {},
    }


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _new_id() -> str:
    import uuid

    return str(uuid.uuid4())


async def _ensure_source_text(ctx: AgentContext, text: Optional[str]) -> str:
    """
    取待处理文本：显式传入 > 上下文现有文本 > 自动解析当前文档。

    自动解析让工具在模型忘记先调用 parse_document 时也能正常工作，
    减少无谓的失败往返。
    """
    if text and text.strip():
        return text
    current = ctx.current_text(None)
    if current.strip():
        return current
    if ctx.file_path:
        await parse_document(ctx)
        return ctx.current_text(None)
    raise ValueError("没有可处理的内容（请先解析文档或提供 text 参数）")


def _truncate(text: str, limit: int = MAX_LLM_INPUT_CHARS) -> tuple[str, bool]:
    """超长文本截断，返回 (文本, 是否被截断)"""
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _collect_tables(parsed) -> List[Dict[str, Any]]:
    """从解析结果的正文里还原表格块（带页码）"""
    tables: List[Dict[str, Any]] = []
    pages = parsed.pages or [parsed.text]
    for page_no, page_text in enumerate(pages, start=1):
        for match in re.finditer(r"\[表格 \d+\]\n((?:\|.*\n?)+)", page_text):
            markdown = match.group(1).strip()
            tables.append(
                {
                    "page": page_no,
                    "markdown": markdown,
                    "rows": len([ln for ln in markdown.splitlines() if ln.startswith("|")]),
                }
            )
    return tables


def _parse_page_range(page_range: Optional[str]) -> Optional[set]:
    """'1-3' / '2' → {1,2,3} / {2}；None → None（表示全部）"""
    if not page_range:
        return None
    pages: set = set()
    for part in str(page_range).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, _, end = part.partition("-")
            if start.strip().isdigit() and end.strip().isdigit():
                pages.update(range(int(start), int(end) + 1))
        elif part.isdigit():
            pages.add(int(part))
    return pages or None


def _register_document(
    ctx: AgentContext, doc_id: str, texts: List[str], metadata: Optional[Dict[str, Any]]
) -> None:
    """在业务库登记文档记录，使 Agent 入库的内容出现在文档管理列表中"""
    from app.database import SessionLocal
    from app.models.document import Document

    # 显式导入外键目标模型：脚本/独立调用场景下需保证 metadata 中已注册
    # users / tenants 表，否则 Document 的外键解析会失败
    from app.models import tenant as _tenant_model  # noqa: F401
    from app.models import user as _user_model  # noqa: F401

    with SessionLocal() as db:
        existing = db.query(Document).filter(Document.id == doc_id).first()
        if existing is not None:
            existing.chunk_count = len(texts)
            db.commit()
            return
        db.add(
            Document(
                id=doc_id,
                tenant_id=ctx.tenant_id,
                file_name=ctx.file_name or "agent_output",
                file_type="agent",
                file_size=sum(len(t) for t in texts),
                chunk_count=len(texts),
                chunk_strategy="paragraphs",
                visibility=ctx.visibility,
                allowed_roles=ctx.allowed_roles,
                uploader_id=ctx.user_id,
            )
        )
        db.commit()
