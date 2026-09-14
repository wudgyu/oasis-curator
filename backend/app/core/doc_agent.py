"""
文档处理 Agent（Function Calling 实战）

LLM 依据用户需求自主决定调用哪些工具、按什么顺序执行，工具结果回传后
继续决策，直到产出最终答复。全程记录执行轨迹（AgentStep），供前端展示。

两种编排模式：
- native：模型原生 Function Calling（tools 参数 + tool_calls 回传）
- prompt：Prompt 注入降级（把工具清单写进提示词，要求模型输出 JSON 指令），
          用于不支持原生工具调用的模型

工具实现见 core/agent_tools.py；新增工具无需改动本模块。
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

from app.core.agent_tools import (
    AgentContext,
    describe_tools,
    execute_tool,
    get_tool_schemas,
)
from app.core.llm_provider import LLMProvider, llm_provider

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 6
RESULT_PREVIEW_CHARS = 400
MODE_NATIVE = "native"
MODE_PROMPT = "prompt"
MODE_AUTO = "auto"

# 判定"模型不支持原生工具调用"的错误特征（命中即自动降级为 Prompt 注入）
_TOOLS_UNSUPPORTED_HINTS = (
    "does not support tools",
    "tools is not supported",
    "unsupported parameter",
    "unknown parameter",
    "unrecognized request argument",
    "invalid parameter",
    "function calling",
    "tool_calls",
    "tools",
)

# 已确认不支持原生工具调用的 provider（同进程内缓存，避免每次重复失败）
_PROMPT_ONLY_PROVIDERS: set = set()

SYSTEM_PROMPT = """你是 Oasis Curator 的文档处理 Agent，负责根据用户需求编排文档处理流程。

工作原则：
1. 先解析后处理：涉及文档内容的操作，先用 parse_document 获取内容
2. 按需调用工具，不要调用与需求无关的工具；能一步完成的不要拆成多步
3. 多数工具的文本参数可省略——省略时自动作用于当前文档内容，无需把文档原文放进参数
4. 工具失败时会返回 error 字段：向用户说明失败原因，并给出可行的替代方案
5. 任务完成后用中文简要汇报：做了什么、产出是什么（字数、表格数、入库块数等关键数字）

可用工具：
{tools}
"""

PROMPT_INJECTION_TEMPLATE = """可用工具：
{tools}

调用工具时，只输出如下 JSON（不要有其他内容）：
{{"tool": "工具名", "args": {{"参数名": "参数值"}}}}

任务完成或无需调用工具时，输出：
{{"final": "给用户的最终答复"}}

示例：
用户：帮我看看文档有多少页
助手：{{"tool": "parse_document", "args": {{}}}}
（收到工具结果后）
助手：{{"final": "文档共 3 页。"}}
"""

# 降级模式下模型未按协议输出时的纠偏提示（每轮任务最多纠正一次）
PROMPT_NUDGE = (
    "请严格按约定格式回复：需要调用工具时输出 "
    '{"tool": "工具名", "args": {...}}；任务已完成时输出 {"final": "最终答复"}。'
    "不要输出其他格式的内容。"
)


@dataclass
class AgentStep:
    """一次工具调用的执行记录"""

    index: int
    tool: str
    args: Dict[str, Any]
    ok: bool
    elapsed_ms: int
    result_preview: str = ""
    error: Optional[str] = None
    result: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "tool": self.tool,
            "args": self.args,
            "ok": self.ok,
            "elapsed_ms": self.elapsed_ms,
            "result_preview": self.result_preview,
            "error": self.error,
            "result": self.result,
        }


@dataclass
class AgentRun:
    """一次 Agent 运行的完整结果"""

    instruction: str
    answer: str = ""
    steps: List[AgentStep] = field(default_factory=list)
    provider: str = ""
    model: str = ""
    mode: str = MODE_NATIVE
    iterations: int = 0
    finished: bool = True  # False = 达到迭代上限仍未收敛

    def to_dict(self) -> Dict[str, Any]:
        return {
            "instruction": self.instruction,
            "answer": self.answer,
            "steps": [s.to_dict() for s in self.steps],
            "provider": self.provider,
            "model": self.model,
            "mode": self.mode,
            "iterations": self.iterations,
            "finished": self.finished,
        }


def _is_tools_unsupported(error: Exception) -> bool:
    """
    判断异常是否表示"模型不支持原生工具调用"。

    逐层查看异常链（LLMProvider 会包装成 RuntimeError 并保留原始异常为 __cause__），
    命中特征词即认为需要降级。属于尽力而为的启发式：宁可漏判（继续报错给用户）
    也不误判（把网络抖动当成不支持而长期降级）。
    """
    texts = [str(error)]
    cause = error.__cause__
    while cause is not None:
        texts.append(str(cause))
        cause = cause.__cause__
    lowered = " ".join(texts).lower()
    return any(hint in lowered for hint in _TOOLS_UNSUPPORTED_HINTS)


def _preview(result: Dict[str, Any]) -> str:
    """工具结果的可读摘要（截断），用于轨迹展示"""
    payload = {k: v for k, v in result.items() if k not in ("ok", "tool")}
    text = json.dumps(payload, ensure_ascii=False)
    return text[:RESULT_PREVIEW_CHARS] + ("…" if len(text) > RESULT_PREVIEW_CHARS else "")


class DocumentAgent:
    """
    文档处理 Agent

    用法：
        agent = DocumentAgent()
        run = await agent.run("把这份文档解析并入库", ctx)
        for step in run.steps: print(step.tool, step.ok)
    """

    def __init__(
        self,
        llm: Optional[LLMProvider] = None,
        max_iterations: int = DEFAULT_MAX_ITERATIONS,
    ) -> None:
        self._llm = llm or llm_provider
        self._max_iterations = max_iterations

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    async def run(
        self,
        instruction: str,
        ctx: AgentContext,
        provider: Optional[str] = None,
        mode: str = MODE_AUTO,
        on_step: Optional[Callable[[AgentStep], Any]] = None,
    ) -> AgentRun:
        """
        执行一次文档处理任务。

        Args:
            instruction: 用户自然语言需求
            ctx: 执行上下文（文档、租户、可见性等）
            provider: 指定 LLM provider，None 走默认 + 降级链
            mode: native（原生工具调用）/ prompt（注入降级）/
                  auto（先原生，模型不支持时自动降级，默认）
            on_step: 每完成一次工具调用后的回调（进度推送）

        Returns:
            AgentRun：最终答复 + 执行轨迹（mode 字段记录实际使用的模式）
        """
        if mode != MODE_AUTO:
            return await self._run_loop(instruction, ctx, provider, mode, on_step)

        # auto：已知不支持原生工具调用的 provider 直接走降级模式
        if provider and provider in _PROMPT_ONLY_PROVIDERS:
            return await self._run_loop(instruction, ctx, provider, MODE_PROMPT, on_step)

        try:
            return await self._run_loop(instruction, ctx, provider, MODE_NATIVE, on_step)
        except Exception as e:  # noqa: BLE001  需按错误特征决定是否降级
            if not _is_tools_unsupported(e):
                raise
            logger.warning(
                "provider=%s 不支持原生工具调用，降级为 Prompt 注入模式: %s", provider, e
            )
            if provider:
                _PROMPT_ONLY_PROVIDERS.add(provider)
            return await self._run_loop(instruction, ctx, provider, MODE_PROMPT, on_step)

    async def _run_loop(
        self,
        instruction: str,
        ctx: AgentContext,
        provider: Optional[str],
        mode: str,
        on_step: Optional[Callable[[AgentStep], Any]],
    ) -> AgentRun:
        """Agent 主循环：模型决策 → 执行工具 → 结果回传 → 继续决策"""
        run = AgentRun(instruction=instruction, mode=mode)
        messages = self._build_messages(instruction, ctx, mode)
        nudged = False  # 降级模式下的协议纠偏是否已用过

        for iteration in range(1, self._max_iterations + 1):
            run.iterations = iteration
            response = await self._llm.chat(
                messages,
                provider=provider,
                temperature=1.0,
                max_tokens=2048,
                tools=get_tool_schemas() if mode == MODE_NATIVE else None,
            )
            run.provider = response.provider
            run.model = response.model

            calls = (
                self._parse_native_calls(response)
                if mode == MODE_NATIVE
                else self._parse_prompt_calls(response.content)
            )

            # 无工具调用 → 通常视为模型给出最终答复
            if not calls:
                # 降级模式下模型可能忽略 JSON 协议直接作答（尚未调用过任何工具时）：
                # 纠偏一次，让它按协议重新决策，提升 fallback 的可靠性
                if mode == MODE_PROMPT and not nudged and not run.steps:
                    nudged = True
                    messages.append({"role": "assistant", "content": response.content or ""})
                    messages.append({"role": "user", "content": PROMPT_NUDGE})
                    logger.info("降级模式：模型未按协议输出，已发送纠偏提示")
                    continue
                run.answer = self._extract_answer(response.content, mode)
                return run

            # 有工具调用 → 逐个执行并把结果回传模型
            assistant_message = self._assistant_message(response.content, calls, mode)
            messages.append(assistant_message)
            for index, call in enumerate(calls, start=len(run.steps) + 1):
                step, tool_message = await self._run_call(ctx, index, call, mode)
                run.steps.append(step)
                messages.append(tool_message)
                if on_step:
                    result = on_step(step)
                    if asyncio.iscoroutine(result):
                        await result

        # 达到迭代上限仍未收敛：保留已完成的步骤，给出显式提示
        run.finished = False
        done = "、".join(s.tool for s in run.steps) or "（无）"
        run.answer = (
            f"任务未能在 {self._max_iterations} 轮内完成，已执行的步骤：{done}。"
            f"建议把需求拆分成更具体的指令后重试。"
        )
        return run

    async def run_stream(
        self,
        instruction: str,
        ctx: AgentContext,
        provider: Optional[str] = None,
        mode: str = MODE_NATIVE,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        流式执行：每步工具调用产出一个事件，最后产出最终答复。

        事件：{"type": "step", ...} / {"type": "done", ...} / {"type": "error", "message": ...}
        """
        queue: asyncio.Queue = asyncio.Queue()
        sentinel = object()

        async def collect(step: AgentStep) -> None:
            await queue.put({"type": "step", **step.to_dict()})

        async def worker() -> None:
            try:
                run = await self.run(instruction, ctx, provider, mode, on_step=collect)
                await queue.put({"type": "done", **run.to_dict()})
            except Exception as e:  # noqa: BLE001  流式过程中需通知前端
                logger.exception("Agent 执行失败")
                await queue.put({"type": "error", "message": str(e)})
            finally:
                await queue.put(sentinel)  # type: ignore[arg-type]

        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                yield item
        finally:
            if not task.done():
                task.cancel()

    # ------------------------------------------------------------------
    # 内部：消息构造与解析
    # ------------------------------------------------------------------

    def _build_messages(
        self, instruction: str, ctx: AgentContext, mode: str
    ) -> List[Dict[str, Any]]:
        system = SYSTEM_PROMPT.format(tools=describe_tools())
        if mode == MODE_PROMPT:
            system += "\n" + PROMPT_INJECTION_TEMPLATE.format(tools=describe_tools())

        document_hint = (
            f"当前文档：{ctx.file_name}（已上传，可直接用工具处理）"
            if ctx.file_name
            else "当前没有上传文档，如需处理文档请告知用户先上传"
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": f"{document_hint}\n\n用户需求：{instruction}"},
        ]

    @staticmethod
    def _parse_native_calls(response) -> List[Dict[str, Any]]:
        """原生模式：解析 tool_calls"""
        calls = []
        for call in response.tool_calls:
            try:
                args = json.loads(call.arguments) if call.arguments else {}
            except json.JSONDecodeError:
                args = {"__raw__": call.arguments}
            calls.append({"id": call.id, "name": call.name, "args": args})
        return calls

    @staticmethod
    def _parse_prompt_calls(content: str) -> List[Dict[str, Any]]:
        """
        降级模式：从模型输出里解析 JSON 指令。

        容忍 ```json 包裹与前后缀文本；解析不出工具名视为任务结束。
        """
        text = (content or "").strip()
        if not text:
            return []
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            return []
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return []
        tool_name = payload.get("tool")
        if not tool_name:
            return []
        return [
            {
                "id": f"prompt-{int(time.time() * 1000)}",
                "name": tool_name,
                "args": payload.get("args") or {},
            }
        ]

    @staticmethod
    def _extract_answer(content: str, mode: str) -> str:
        """最终答复：降级模式下优先取 final 字段"""
        text = (content or "").strip()
        if mode == MODE_PROMPT:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end > start:
                try:
                    payload = json.loads(text[start : end + 1])
                    if payload.get("final"):
                        return str(payload["final"])
                except json.JSONDecodeError:
                    pass
        return text

    def _assistant_message(
        self, content: str, calls: List[Dict[str, Any]], mode: str
    ) -> Dict[str, Any]:
        """构造回传给模型的历史消息（原生模式需保留 tool_calls 结构）"""
        if mode == MODE_PROMPT:
            return {"role": "assistant", "content": content or ""}
        return {
            "role": "assistant",
            "content": content or "",
            "tool_calls": [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(call["args"], ensure_ascii=False),
                    },
                }
                for call in calls
            ],
        }

    async def _run_call(
        self, ctx: AgentContext, index: int, call: Dict[str, Any], mode: str
    ) -> tuple[AgentStep, Dict[str, Any]]:
        """
        执行一次工具调用，返回 (轨迹记录, 回传模型的消息)。

        回传格式随模式不同：
        - native：tool 角色消息（必须能对应上 assistant 的 tool_calls）
        - prompt：降级模式没有 tool_calls 结构，工具结果以 user 消息形式追加
          （若仍用 tool 角色，服务端会以 "must be a response to tool_calls" 拒绝）
        """
        started = time.monotonic()
        result = await execute_tool(ctx, call["name"], call.get("args") or {})
        elapsed_ms = int((time.monotonic() - started) * 1000)

        step = AgentStep(
            index=index,
            tool=call["name"],
            args=call.get("args") or {},
            ok=bool(result.get("ok")),
            elapsed_ms=elapsed_ms,
            result_preview=_preview(result),
            error=result.get("error"),
            result=result,
        )
        logger.info(
            "Agent 步骤 %d: %s(%s) → %s（%dms）",
            index,
            step.tool,
            json.dumps(step.args, ensure_ascii=False)[:120],
            "成功" if step.ok else f"失败: {step.error}",
            elapsed_ms,
        )
        payload = json.dumps(result, ensure_ascii=False)
        if mode == MODE_NATIVE:
            message = {"role": "tool", "tool_call_id": call["id"], "content": payload}
        else:
            message = {
                "role": "user",
                "content": f"工具 {call['name']} 执行结果：{payload}\n\n"
                f"如需继续调用工具，请输出 JSON 指令；否则输出 final 给出最终答复。",
            }
        return step, message


# 模块级实例：供 API 与脚本直接使用
doc_agent = DocumentAgent()
