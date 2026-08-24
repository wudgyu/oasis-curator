#!/usr/bin/env python3
"""
ChromaDB 初始化脚本

在 ChromaDB 服务端创建项目使用的命名空间：
- tenant  : curator（项目命名空间，对应产品品牌）
- database: oasis（向量库）

幂等：已存在时跳过，可重复执行。

用法:
    python scripts/init_chroma.py
    环境变量: CHROMA_HOST / CHROMA_PORT / CHROMA_TENANT / CHROMA_DATABASE
"""

import argparse
import os
import sys

import httpx

# 确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core import _sqlite_compat  # noqa: F401, E402  必须在 import chromadb 之前
from app.core.config import settings  # noqa: E402


class Colors:
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    BOLD = "\033[1m"
    END = "\033[0m"


def _create_entity(base_url: str, path: str, name: str, entity: str) -> str:
    """
    调用 REST 创建实体，幂等处理。

    Returns:
        "created" / "exists"
    """
    resp = httpx.post(f"{base_url}{path}", json={"name": name}, timeout=10)
    if resp.status_code in (200, 201):
        return "created"
    # 已存在：GET 能查到即视为 OK（Chroma 对重复创建返回 4xx）
    get_resp = httpx.get(f"{base_url}{path}/{name}", timeout=10)
    if get_resp.status_code == 200:
        return "exists"
    raise RuntimeError(
        f"创建 {entity} '{name}' 失败（HTTP {resp.status_code}: {resp.text[:200]}），"
        f"且 GET 校验也失败（HTTP {get_resp.status_code}）"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ChromaDB 初始化")
    parser.add_argument("--host", default=settings.CHROMA_HOST)
    parser.add_argument("--port", type=int, default=settings.CHROMA_PORT)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}/api/v2"
    tenant = settings.CHROMA_TENANT
    database = settings.CHROMA_DATABASE

    # 1. 服务健康检查
    heartbeat = httpx.get(f"{base_url}/heartbeat", timeout=10)
    if heartbeat.status_code != 200:
        print(f"{Colors.RED}✗ ChromaDB 服务不可达: {base_url}{Colors.END}")
        sys.exit(1)
    version = httpx.get(f"{base_url}/version", timeout=10).json()
    print(f"{Colors.BOLD}✓ ChromaDB 服务正常（版本 {version}）{Colors.END}")

    # 2. 创建租户与数据库（幂等）
    for entity, path, name in (
        ("租户", "/tenants", tenant),
        ("数据库", f"/tenants/{tenant}/databases", database),
    ):
        result = _create_entity(base_url, path, name, entity)
        label = f"{Colors.GREEN}创建{Colors.END}" if result == "created" else f"{Colors.YELLOW}已存在，跳过{Colors.END}"
        print(f"  {entity} {name}: {label}")

    # 3. 客户端连接校验
    import chromadb

    client = chromadb.HttpClient(
        host=args.host, port=args.port, tenant=tenant, database=database
    )
    collections = client.list_collections()
    print(
        f"{Colors.BOLD}✓ 客户端连接 tenant={tenant}, database={database} 成功，"
        f"现有 collection {len(collections)} 个{Colors.END}"
    )


if __name__ == "__main__":
    main()
