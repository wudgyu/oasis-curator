#!/usr/bin/env python3
"""
CLI 多模型聊天工具

支持 DeepSeek / Kimi / Ark 多模型切换，流式输出，多轮对话上下文管理。

用法:
    python scripts/cli_chat.py
    python scripts/cli_chat.py --provider kimi
    python scripts/cli_chat.py --system "你是一个 Python 编程专家"

特殊命令:
    /clear   清空对话历史
    /history 查看当前消息数
    /exit    退出
"""

import argparse
import asyncio
import os
import signal
import sys
from typing import List, Optional

# 确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.llm_provider import LLMProvider, LLMResponse, llm_provider


# ---------------------------------------------------------------------------
# 终端颜色
# ---------------------------------------------------------------------------

class Colors:
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    GRAY = "\033[90m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# ---------------------------------------------------------------------------
# ChatSession
# ---------------------------------------------------------------------------


class ChatSession:
    """管理单次对话会话的上下文和统计"""

    def __init__(self, system_prompt: Optional[str] = None, provider: str = "deepseek") -> None:
        self._system_prompt = system_prompt
        self._provider_name = provider
        self._llm = LLMProvider(provider=provider)
        self._messages: List[dict] = []
        self._cumulative_tokens = 0
        self._round_count = 0
        self._last_round_tokens = 0

        if system_prompt:
            self._messages.append({"role": "system", "content": system_prompt})

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def round_count(self) -> int:
        return self._round_count

    @property
    def cumulative_tokens(self) -> int:
        return self._cumulative_tokens

    @property
    def last_round_tokens(self) -> int:
        return self._last_round_tokens

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def last_answer_provider(self) -> Optional[str]:
        """最近一轮实际应答的模型（降级后为降级链上的模型）"""
        return self._llm.last_provider

    def add_user_message(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        self._messages.append({"role": "assistant", "content": content})

    def clear(self) -> None:
        """清空对话历史，保留 system prompt"""
        system_msg = self._messages[0] if self._messages and self._messages[0]["role"] == "system" else None
        self._messages = [system_msg] if system_msg else []

    async def chat(self) -> LLMResponse:
        """发送当前消息列表，返回 LLM 响应"""
        self._round_count += 1
        response = await self._llm.chat(self._messages)
        if response.usage:
            self._last_round_tokens = response.usage.total_tokens
            self._cumulative_tokens += response.usage.total_tokens
        self.add_assistant_message(response.content)
        return response

    async def chat_stream(self):
        """流式发送当前消息列表，逐 token 打印，并统计 Token 用量"""
        self._round_count += 1
        self._last_round_tokens = 0

        # 流式输出文本
        full_content = ""
        async for token in self._llm.chat_stream(self._messages):
            full_content += token
            sys.stdout.write(token)
            sys.stdout.flush()

        # 流式完成后追加到消息历史
        self.add_assistant_message(full_content)

        # Token 统计：优先取流式响应自带的 usage（以实际应答模型为准）
        usage = self._llm.last_usage
        if usage is None:
            # 模型流式响应不含 usage 时，向实际应答模型发起轻量调用估算
            answering = self._llm.last_provider or self._provider_name
            try:
                stats = await self._llm.chat(
                    [{"role": "user", "content": "ping"}],
                    provider=answering,
                    max_tokens=1,
                )
                usage = stats.usage
            except Exception:
                pass  # 统计失败不影响主流程
        if usage:
            self._last_round_tokens = usage.total_tokens
            self._cumulative_tokens += usage.total_tokens


# ---------------------------------------------------------------------------
# 命令处理
# ---------------------------------------------------------------------------


def print_banner(provider: str, system_prompt: Optional[str]) -> None:
    """打印欢迎横幅"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════════╗{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}   {Colors.BOLD}Oasis Curator · CLI Chat{Colors.RESET}           {Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}╠══════════════════════════════════════════╣{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  Provider : {Colors.GREEN}{provider:<30}{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
    if system_prompt:
        display = system_prompt[:26] + "..." if len(system_prompt) > 26 else system_prompt
        print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  System   : {Colors.YELLOW}{display:<30}{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}╠══════════════════════════════════════════╣{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  /clear  清空历史  /history 查看上下文  {Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}║{Colors.RESET}  /exit   退出对话                       {Colors.BOLD}{Colors.CYAN}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}╚══════════════════════════════════════════╝{Colors.RESET}\n")


def handle_command(cmd: str, session: ChatSession) -> bool:
    """
    处理特殊命令。

    Returns:
        True 表示继续对话，False 表示退出
    """
    cmd = cmd.strip().lower()

    if cmd == "/exit":
        print(f"\n{Colors.GRAY}👋 再见！本次对话共 {session.round_count} 轮，累计消耗 ~{session.cumulative_tokens} tokens{Colors.RESET}\n")
        return False

    if cmd == "/clear":
        session.clear()
        print(f"{Colors.GREEN}✅ 对话历史已清空（system prompt 保留）{Colors.RESET}\n")
        return True

    if cmd == "/history":
        msg_count = session.message_count
        print(f"{Colors.CYAN}📋 当前上下文: {msg_count} 条消息, {session.round_count} 轮对话, 累计 ~{session.cumulative_tokens} tokens{Colors.RESET}\n")
        return True

    return True


# ---------------------------------------------------------------------------
# REPL 主循环
# ---------------------------------------------------------------------------


async def run_repl(
    provider: str,
    system_prompt: Optional[str] = None,
) -> None:
    """运行 REPL 交互循环"""
    session = ChatSession(system_prompt=system_prompt, provider=provider)

    print_banner(provider, system_prompt)

    # 检查 provider 可用性
    if provider not in LLMProvider.available_providers():
        print(f"{Colors.YELLOW}⚠  Provider '{provider}' 未配置 API Key，请设置环境变量后重试{Colors.RESET}")
        print(f"   export DEEPSEEK_API_KEY=sk-xxx  # DeepSeek")
        print(f"   export KIMI_API_KEY=sk-xxx      # Kimi")
        print(f"   export ARK_API_KEY=xxx           # Ark\n")
        return

    while True:
        try:
            # 读取用户输入
            user_input = input(f"{Colors.BOLD}{Colors.GREEN}你 › {Colors.RESET}")
        except (EOFError, KeyboardInterrupt):
            print(f"\n{Colors.GRAY}👋 再见！{Colors.RESET}\n")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # 处理特殊命令
        if user_input.startswith("/"):
            if not handle_command(user_input, session):
                break
            continue

        # 添加用户消息到上下文
        session.add_user_message(user_input)

        # 流式输出 AI 回复
        print(f"{Colors.BOLD}{Colors.CYAN}AI › {Colors.RESET}", end="", flush=True)
        try:
            await session.chat_stream()
        except RuntimeError as e:
            print(f"\n{Colors.RED}❌ 调用失败: {e}{Colors.RESET}")
            # 移除失败的用户消息，避免污染上下文
            if session._messages and session._messages[-1]["role"] == "user":
                session._messages.pop()
            continue

        print()  # 换行

        # 打印 token 统计（降级时标注实际应答模型）
        stats = f"[本轮 #{session.round_count}"
        answered_by = session.last_answer_provider
        if answered_by and answered_by != session.provider_name:
            stats += f" · 降级至 {answered_by}"
        if session.last_round_tokens:
            stats += f" · 本轮 ~{session.last_round_tokens} tokens"
        stats += f" · 累计 ~{session.cumulative_tokens} tokens]"
        print(f"{Colors.GRAY}{stats}{Colors.RESET}")
        print()


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Oasis Curator · CLI 多模型聊天工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s
  %(prog)s --provider kimi
  %(prog)s --system "你是一个 Python 编程专家"
  %(prog)s --provider ark --system "你是一个知识渊博的助手"
        """,
    )
    parser.add_argument(
        "--provider",
        choices=["deepseek", "kimi", "ark"],
        default="deepseek",
        help="LLM 模型提供商 (default: deepseek)",
    )
    parser.add_argument(
        "--system",
        type=str,
        default=None,
        help="System Prompt，定义 AI 的角色和行为",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run_repl(provider=args.provider, system_prompt=args.system))


if __name__ == "__main__":
    main()