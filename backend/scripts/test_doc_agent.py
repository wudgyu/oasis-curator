#!/usr/bin/env python3
"""
文档处理 Agent 循环自测（确定性，不依赖真实模型）

用脚本化的 FakeLLM 驱动 Agent，验证编排机制而非模型能力：
- 单步工具调用 → 最终答复
- 多步串行编排（parse → summarize → index），校验工具顺序与消息回传
- 工具失败 → 错误回传模型 → 模型给出替代方案
- 达到迭代上限 → 不收敛标记 + 已执行步骤汇总
- Prompt 注入降级模式的指令解析与 final 提取
- 模型返回非法 JSON 参数时的容错

运行：python scripts/test_doc_agent.py（不需要 LLM Key，index_chunks 会真实入库后清理）
"""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.agent_tools import AgentContext  # noqa: E402
from app.core.doc_agent import MODE_NATIVE, MODE_PROMPT, DocumentAgent  # noqa: E402
from app.core.llm_provider import LLMResponse, LLMToolCall  # noqa: E402
from app.core.vector_store import vector_store  # noqa: E402

SAMPLE_PDF = BACKEND_DIR / "data" / "samples" / "oasis_curator_api_reference.pdf"

TEST_TENANT = "agent-loop-test"
TEST_USER = "loop-tester"

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


class FakeLLM:
    """
    脚本化 LLM：按预设脚本依次返回响应。

    script 中每项为 (tool_calls, content)：
    - tool_calls: [(name, args_dict), ...]，非空表示请求调用工具
    - content: 文本内容（无工具调用时作为最终答复）
    """

    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls: list = []  # 记录每次收到的消息，便于断言上下文回传
        self.last_provider = "fake"
        self.last_usage = None

    async def chat(self, messages, provider=None, temperature=None, max_tokens=None, tools=None, tool_choice=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        if not self._script:
            return LLMResponse(content="（脚本已耗尽）", model="fake", provider="fake")
        tool_calls, content = self._script.pop(0)
        return LLMResponse(
            content=content,
            model="fake-model",
            provider="fake",
            tool_calls=[
                LLMToolCall(id=f"call-{i}", name=name, arguments=json.dumps(args, ensure_ascii=False))
                for i, (name, args) in enumerate(tool_calls or [])
            ],
        )


def make_ctx() -> AgentContext:
    return AgentContext(
        tenant_id=TEST_TENANT,
        user_id=TEST_USER,
        file_path=str(SAMPLE_PDF),
        file_name=SAMPLE_PDF.name,
    )


async def test_single_step() -> None:
    print("\n[1] 单步工具调用 → 最终答复")
    llm = FakeLLM(
        [
            ([("parse_document", {})], ""),
            ([], "文档已解析完成，共 3 页。"),
        ]
    )
    agent = DocumentAgent(llm=llm)
    run = await agent.run("解析这份文档", make_ctx())

    check("执行 1 个工具步骤", len(run.steps), 1)
    check("工具为 parse_document", run.steps[0].tool, "parse_document")
    check("步骤成功", run.steps[0].ok, True)
    check("最终答复取自模型", run.answer, "文档已解析完成，共 3 页。")
    check("迭代 2 轮", run.iterations, 2)
    check("正常收敛", run.finished, True)
    check("原生模式传入工具定义", len(llm.calls[0]["tools"] or []), 5)

    # 第二轮请求应包含 tool 角色消息（工具结果已回传）
    second_messages = llm.calls[1]["messages"]
    check("工具结果以 tool 角色回传", any(m.get("role") == "tool" for m in second_messages), True)
    check(
        "assistant 消息保留 tool_calls 结构",
        any(m.get("role") == "assistant" and m.get("tool_calls") for m in second_messages),
        True,
    )


async def test_multi_step_chain() -> None:
    print("\n[2] 多步串行编排（parse → summarize → index）")
    llm = FakeLLM(
        [
            ([("parse_document", {})], ""),
            ([("summarize_text", {"max_length": 100})], ""),
            ([("index_chunks", {"chunks": ["摘要内容一", "摘要内容二"]})], ""),
            ([], "已完成解析、摘要与入库。"),
        ]
    )
    ctx = make_ctx()
    agent = DocumentAgent(llm=llm)
    run = await agent.run("解析、摘要后入库", ctx)

    check("执行 3 个步骤", [s.tool for s in run.steps], ["parse_document", "summarize_text", "index_chunks"])
    check("全部成功", all(s.ok for s in run.steps), True)
    check("入库块数正确", run.steps[2].result["chunk_count"], 2)
    check("上下文记录文档 ID", bool(ctx.document_id), True)
    check("步骤序号连续", [s.index for s in run.steps], [1, 2, 3])

    # 清理入库产物
    if ctx.document_id:
        vector_store.delete_document(ctx.document_id, TEST_TENANT)
        from app.database import SessionLocal
        from app.models.document import Document

        with SessionLocal() as db:
            db.query(Document).filter(Document.id == ctx.document_id).delete()
            db.commit()


async def test_tool_failure_feedback() -> None:
    print("\n[3] 工具失败 → 错误回传 → 替代方案")
    llm = FakeLLM(
        [
            ([("parse_document", {"file_path": "../../etc/passwd"})], ""),
            ([], "该文件无法访问（路径越界），请重新上传文档后我再处理。"),
        ]
    )
    agent = DocumentAgent(llm=llm)
    run = await agent.run("解析 /etc/passwd", make_ctx())

    check("步骤标记为失败", run.steps[0].ok, False)
    check("错误信息含越界提示", "越界" in (run.steps[0].error or ""), True)
    check("模型给出替代方案", "请重新上传" in run.answer, True)

    # 回传给模型的 tool 消息应包含错误内容
    tool_message = next(
        m for m in llm.calls[1]["messages"] if m.get("role") == "tool"
    )
    check("错误随工具结果回传", "越界" in tool_message["content"], True)


async def test_max_iterations() -> None:
    print("\n[4] 迭代上限保护")
    # 模型每轮都调用工具，永不收敛
    llm = FakeLLM([([("parse_document", {})], "")] * 10)
    agent = DocumentAgent(llm=llm, max_iterations=3)
    run = await agent.run("无限调用工具", make_ctx())

    check("标记为未收敛", run.finished, False)
    check("步骤数受上限约束", len(run.steps), 3)
    check("答复说明未完成", "未能在 3 轮内完成" in run.answer, True)
    check("答复列出已执行步骤", "parse_document" in run.answer, True)


async def test_prompt_mode() -> None:
    print("\n[5] Prompt 注入降级模式")
    llm = FakeLLM(
        [
            ([], '```json\n{"tool": "parse_document", "args": {}}\n```'),
            ([], '{"final": "已按注入模式完成解析。"}'),
        ]
    )
    agent = DocumentAgent(llm=llm)
    run = await agent.run("解析文档", make_ctx(), mode=MODE_PROMPT)

    check("降级模式不传 tools 参数", llm.calls[0]["tools"], None)
    check("解析出工具调用", [s.tool for s in run.steps], ["parse_document"])
    check("从 final 字段取答复", run.answer, "已按注入模式完成解析。")
    check("运行模式标记正确", run.mode, MODE_PROMPT)
    check(
        "系统提示含工具清单与 JSON 协议",
        "调用工具时" in llm.calls[0]["messages"][0]["content"],
        True,
    )


async def test_malformed_args() -> None:
    print("\n[6] 非法参数容错")
    llm = FakeLLM(
        [
            ([("translate_text", {"target_lang": "中文"})], ""),
            ([], "翻译完成。"),
        ]
    )
    agent = DocumentAgent(llm=llm)
    run = await agent.run("翻译文档", make_ctx())

    check("参数缺失时仍可执行（取上下文）", run.steps[0].ok, True)
    check("翻译结果进入上下文预览", bool(run.steps[0].result_preview), True)


async def main() -> None:
    await test_single_step()
    await test_multi_step_chain()
    await test_tool_failure_feedback()
    await test_max_iterations()
    await test_prompt_mode()
    await test_malformed_args()

    print(f"\n{'=' * 50}\n通过 {passed} / {passed + failed}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
