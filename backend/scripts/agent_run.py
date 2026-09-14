#!/usr/bin/env python3
"""
文档处理 Agent CLI

观察 LLM 如何依据需求自主选择工具与执行顺序，打印每一步的参数、耗时与结果摘要。

用法:
    python scripts/agent_run.py --file <文档> --instruction "把这份文档解析、摘要后入库"
    python scripts/agent_run.py --scenario 2                     # 运行预置场景
    python scripts/agent_run.py --scenario all --provider kimi   # 换模型跑全部场景
    python scripts/agent_run.py --scenario 1 --mode prompt       # 强制 Prompt 注入降级模式
    python scripts/agent_run.py --scenario 1 --keep              # 保留入库的文档（默认跑完清理）
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# 确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.agent_tools import AgentContext  # noqa: E402
from app.core.doc_agent import DocumentAgent  # noqa: E402
from app.core.vector_store import vector_store  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "samples"

# 预置场景（对应练习规格中的 4 类用户输入）
SCENARIOS = {
    "1": ("上传这份文档并入库", "oasis_curator_api_reference.pdf"),
    "2": ("这份报告有表格，提取出来", "oasis_curator_api_reference.pdf"),
    "3": ("帮我总结这份文档的核心内容", "oasis_curator_manual.pdf"),
    "4": ("把这份文档解析、摘要后入库", "oasis_curator_api_reference.pdf"),
}


class Colors:
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    GRAY = "\033[90m"
    BOLD = "\033[1m"
    END = "\033[0m"


def resolve_actor(tenant_name: str, username: str) -> tuple[str, str]:
    """按租户名与用户名解析 ID（入库需要真实的租户/用户）"""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.name == tenant_name).first()
        user = db.query(User).filter(User.username == username).first()
        if tenant is None or user is None:
            raise SystemExit(f"租户或用户不存在: {tenant_name} / {username}")
        return tenant.id, user.id
    finally:
        db.close()


async def run_scenario(
    agent: DocumentAgent,
    instruction: str,
    file_name: str,
    tenant_id: str,
    user_id: str,
    provider: str | None,
    mode: str,
    keep: bool,
) -> None:
    """执行一个场景并打印轨迹"""
    file_path = SAMPLE_DIR / file_name
    ctx = AgentContext(
        tenant_id=tenant_id,
        user_id=user_id,
        file_path=str(file_path),
        file_name=file_name,
    )

    print(f"\n{Colors.BOLD}{'=' * 72}{Colors.END}")
    print(f"{Colors.BOLD}需求：{instruction}{Colors.END}")
    print(f"{Colors.GRAY}文档：{file_name} | 模式：{mode} | provider：{provider or '默认'}{Colors.END}")

    run = await agent.run(instruction, ctx, provider=provider, mode=mode)

    print(f"\n{Colors.BOLD}执行轨迹（{len(run.steps)} 步）：{Colors.END}")
    for step in run.steps:
        mark = f"{Colors.GREEN}✓{Colors.END}" if step.ok else f"{Colors.RED}✗{Colors.END}"
        args = ", ".join(f"{k}={str(v)[:40]}" for k, v in step.args.items()) or "（无参数）"
        print(f"  {mark} {Colors.CYAN}{step.index}. {step.tool}{Colors.END}({args}) {Colors.GRAY}{step.elapsed_ms}ms{Colors.END}")
        if step.error:
            print(f"      {Colors.RED}错误：{step.error}{Colors.END}")
        print(f"      {Colors.GRAY}{step.result_preview[:160]}{Colors.END}")

    print(f"\n{Colors.BOLD}最终答复：{Colors.END}")
    print(f"  {run.answer}")
    print(
        f"\n{Colors.GRAY}模型：{run.provider}/{run.model} | 迭代 {run.iterations} 轮 | "
        f"{'已收敛' if run.finished else '未收敛（达到上限）'}{Colors.END}"
    )

    if ctx.document_id and not keep:
        vector_store.delete_document(ctx.document_id, tenant_id)
        db = SessionLocal()
        try:
            from app.models.document import Document

            db.query(Document).filter(Document.id == ctx.document_id).delete()
            db.commit()
        finally:
            db.close()
        print(f"{Colors.GRAY}（已清理入库文档 {ctx.document_id[:8]}）{Colors.END}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="文档处理 Agent CLI")
    parser.add_argument("--file", help="文档文件名（data/samples 或上传目录内）")
    parser.add_argument("--instruction", help="自然语言需求")
    parser.add_argument("--scenario", default=None, help="预置场景编号（1-4 或 all）")
    parser.add_argument("--provider", default=None, help="LLM provider（deepseek/kimi/ark）")
    parser.add_argument("--mode", default="native", choices=["native", "prompt"], help="编排模式")
    parser.add_argument("--tenant", default="星辰科技", help="租户名")
    parser.add_argument("--user", default="zhangsan", help="用户名")
    parser.add_argument("--keep", action="store_true", help="保留入库的文档")
    args = parser.parse_args()

    tenant_id, user_id = resolve_actor(args.tenant, args.user)
    agent = DocumentAgent()

    if args.scenario:
        keys = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
        for key in keys:
            if key not in SCENARIOS:
                raise SystemExit(f"未知场景: {key}（可选 {'/'.join(SCENARIOS)}）")
            instruction, file_name = SCENARIOS[key]
            await run_scenario(
                agent, instruction, file_name, tenant_id, user_id, args.provider, args.mode, args.keep
            )
        return

    if not args.file or not args.instruction:
        raise SystemExit("请提供 --file 与 --instruction，或使用 --scenario")
    await run_scenario(
        agent, args.instruction, args.file, tenant_id, user_id, args.provider, args.mode, args.keep
    )


if __name__ == "__main__":
    asyncio.run(main())
