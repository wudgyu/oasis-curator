#!/usr/bin/env python3
"""
文档处理 Agent 工具集自测（工具层，不含 Agent 循环）

覆盖：
- 工具注册表：Schema 生成、工具清单文本（fallback 用）
- parse_document：PDF/Word 解析、表格收集、上下文写入
- extract_tables：全部表格 / 按页码范围筛选 / 无表格文档
- translate_text / summarize_text：省略参数时取上下文文本（真实调用 LLM）
- index_chunks：切分 → 向量化 → 入库，向量与文档记录可查
- 错误路径：未知工具、路径越界、无内容可处理

运行：python scripts/test_agent_tools.py
（需要向量库可用；translate/summarize/index 需要 LLM Key 与 Embedding 服务）
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent_tools import (  # noqa: E402
    TOOL_REGISTRY,
    AgentContext,
    describe_tools,
    execute_tool,
    get_tool_schemas,
)
from app.core.doc_parser import parse_file  # noqa: E402
from app.core.vector_store import vector_store  # noqa: E402

SAMPLE_DIR = BACKEND_DIR / "data" / "samples"
PDF_WITH_TABLES = SAMPLE_DIR / "oasis_curator_api_reference.pdf"
PDF_PLAIN = SAMPLE_DIR / "oasis_curator_manual.pdf"

TEST_TENANT = "agent-tools-test"
TEST_USER = "tool-tester"

passed = 0
failed = 0


def check(name: str, actual, expected) -> None:
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}：期望 {expected}，实际 {actual}")


def make_ctx(file_path: Path | None = None) -> AgentContext:
    return AgentContext(
        tenant_id=TEST_TENANT,
        user_id=TEST_USER,
        file_path=str(file_path) if file_path else None,
        file_name=file_path.name if file_path else None,
    )


def test_registry() -> None:
    print("\n[1] 工具注册表")
    check("登记 5 个工具", len(TOOL_REGISTRY), 5)
    check(
        "工具名齐全",
        set(TOOL_REGISTRY),
        {"parse_document", "extract_tables", "translate_text", "summarize_text", "index_chunks"},
    )
    schemas = get_tool_schemas()
    check("Schema 为 OpenAI tools 格式", schemas[0]["type"], "function")
    check("Schema 含参数定义", "parameters" in schemas[0]["function"], True)
    check("工具清单文本含全部工具", all(n in describe_tools() for n in TOOL_REGISTRY), True)


async def test_parse() -> None:
    print("\n[2] parse_document")
    ctx = make_ctx(PDF_WITH_TABLES)
    result = await execute_tool(ctx, "parse_document", {})
    check("执行成功", result["ok"], True)
    check("识别为 pdf", result["file_type"], "pdf")
    check("提取到 6 张表格", result["table_count"], 6)
    check("上下文写入解析文本", len(ctx.parsed_text) > 1000, True)
    check("上下文收集表格", len(ctx.tables), 6)
    check("表格带页码", ctx.tables[0]["page"] >= 1, True)


async def test_extract_tables() -> None:
    print("\n[3] extract_tables")
    ctx = make_ctx(PDF_WITH_TABLES)
    result = await execute_tool(ctx, "extract_tables", {})
    check("全部表格", result["table_count"], 6)
    check("返回 Markdown 表格", result["tables"][0]["markdown"].startswith("|"), True)

    filtered = await execute_tool(ctx, "extract_tables", {"page_range": "1"})
    check("按页码筛选（第 1 页）", 0 < filtered["table_count"] < 6, True)

    plain_ctx = make_ctx(PDF_PLAIN)
    none_result = await execute_tool(plain_ctx, "extract_tables", {})
    check("无表格文档返回 0", none_result["table_count"], 0)


async def test_llm_tools() -> None:
    print("\n[4] translate_text / summarize_text（真实调用 LLM）")
    ctx = make_ctx(PDF_WITH_TABLES)
    await execute_tool(ctx, "parse_document", {})

    # 显式传入短文本
    result = await execute_tool(
        ctx, "translate_text", {"text": "Hello, this is a document processing agent.", "target_lang": "中文"}
    )
    check("翻译执行成功", result["ok"], True)
    check("译文含中文", any("一" <= ch <= "鿿" for ch in result["preview"]), True)

    # 省略 text → 使用上下文（此处上下文已是译文，验证取用逻辑）
    ctx.working_text = "The quick brown fox jumps over the lazy dog."
    auto = await execute_tool(ctx, "translate_text", {"target_lang": "中文"})
    check("省略 text 时取上下文", auto["ok"], True)
    check("上下文被更新为译文", ctx.working_text != "The quick brown fox jumps over the lazy dog.", True)

    # 摘要：对解析文档（恢复解析结果后）
    ctx.working_text = ""
    summary = await execute_tool(ctx, "summarize_text", {"max_length": 80})
    check("摘要执行成功", summary["ok"], True)
    check("摘要写入上下文", bool(ctx.summary), True)
    check("摘要长度受控（<= 200 字）", len(ctx.summary) <= 200, True)


async def test_index() -> None:
    print("\n[5] index_chunks（切分 → 向量化 → 入库）")
    ctx = make_ctx(PDF_WITH_TABLES)
    await execute_tool(ctx, "parse_document", {})
    result = await execute_tool(ctx, "index_chunks", {"metadata": {"source": "agent-tools-test"}})
    check("入库执行成功", result["ok"], True)
    check("切分出多个文本块", result["chunk_count"] > 3, True)

    doc_id = result["document_id"]
    check("向量可检索到", vector_store.count(TEST_TENANT) >= result["chunk_count"], True)

    from app.database import SessionLocal
    from app.models.document import Document

    with SessionLocal() as db:
        doc = db.query(Document).filter(Document.id == doc_id).first()
        check("业务库登记文档记录", doc is not None, True)
        check("记录含切分块数", doc.chunk_count, result["chunk_count"])
        check("记录租户正确", doc.tenant_id, TEST_TENANT)

    # 显式传入 chunks
    explicit = await execute_tool(
        ctx, "index_chunks", {"chunks": ["第一段内容", "第二段内容"]}
    )
    check("显式 chunks 入库", explicit["chunk_count"], 2)

    # 清理
    vector_store.delete_document(doc_id, TEST_TENANT)
    vector_store.delete_document(explicit["document_id"], TEST_TENANT)
    with SessionLocal() as db:
        db.query(Document).filter(Document.tenant_id == TEST_TENANT).delete()
        db.commit()


async def test_errors() -> None:
    print("\n[6] 错误路径")
    ctx = make_ctx(PDF_WITH_TABLES)
    unknown = await execute_tool(ctx, "no_such_tool", {})
    check("未知工具返回失败", unknown["ok"], False)
    check("错误信息含可用工具", "可用工具" in unknown["error"], True)

    bad_args = await execute_tool(ctx, "translate_text", {"unknown_param": 1})
    check("参数不合法返回失败", bad_args["ok"], False)

    empty_ctx = make_ctx(None)
    no_doc = await execute_tool(empty_ctx, "parse_document", {})
    check("无文档时解析失败", no_doc["ok"], False)

    traverse = await execute_tool(ctx, "parse_document", {"file_path": "../../../etc/passwd"})
    check("路径越界被拒绝", traverse["ok"], False)
    check("越界错误信息明确", "越界" in traverse["error"], True)

    no_content = await execute_tool(empty_ctx, "summarize_text", {})
    check("无内容摘要返回失败", no_content["ok"], False)


async def main() -> None:
    if not PDF_WITH_TABLES.exists():
        from make_sample_pdf import build_pdf

        sys.path.insert(0, str(BACKEND_DIR / "scripts"))
        build_pdf(SAMPLE_DIR / "oasis_curator_api_reference.md", PDF_WITH_TABLES)

    test_registry()
    await test_parse()
    await test_extract_tables()
    await test_llm_tools()
    await test_index()
    await test_errors()

    print(f"\n{'=' * 50}\n通过 {passed} / {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
