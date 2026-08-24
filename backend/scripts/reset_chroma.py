#!/usr/bin/env python3
"""
ChromaDB 向量索引重建脚本

删除并重建 documents collection（清空全部租户的向量数据）。

使用场景：切换 Embedding 模型后（维度/语义空间不同），旧索引无法复用。

用法:
    python scripts/reset_chroma.py --yes    # 需要显式确认

注意：只清空向量库，业务数据库的 documents 表需另行清理
（或使用 DELETE /api/documents/{id} 逐条删除以保持两边一致）。
"""

import argparse
import os
import sys

# 确保可以导入 app 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core import _sqlite_compat  # noqa: F401, E402
from app.core.config import settings  # noqa: E402
from app.core.vector_store import COLLECTION_NAME  # noqa: E402

import chromadb  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="重建 ChromaDB 向量索引")
    parser.add_argument("--yes", action="store_true", help="确认清空并重建")
    args = parser.parse_args()
    if not args.yes:
        print("此操作会删除全部租户的向量数据，确认请加 --yes 参数")
        sys.exit(1)

    client = chromadb.HttpClient(
        host=settings.CHROMA_HOST,
        port=settings.CHROMA_PORT,
        tenant=settings.CHROMA_TENANT,
        database=settings.CHROMA_DATABASE,
    )

    existing = client.list_collections()
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
        print(f"已删除 collection: {COLLECTION_NAME}")

    client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
    print(f"已重建 collection: {COLLECTION_NAME}（余弦距离空间）")
    print("提示：请重新上传文档；业务数据库中的旧文档记录也请一并清理。")


if __name__ == "__main__":
    main()
