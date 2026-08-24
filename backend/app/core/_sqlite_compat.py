"""
ChromaDB 兼容层（WSL/旧系统专用）

系统自带 sqlite3 低于 3.35.0 时，ChromaDB 在 import 阶段直接报错拒绝启动。
此模块用 pysqlite3-binary（内置新版 SQLite 3.4x+）替换标准库 sqlite3，
使 ChromaDB 在旧系统上可用。

用法：在 import chromadb 之前 import 本模块（embedder.py / vector_store.py
均已内置），替换是幂等的。
"""

import sqlite3
import sys

if sqlite3.sqlite_version_info < (3, 35, 0):
    try:
        import pysqlite3  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "系统 sqlite3 版本过低（<3.35.0）且未安装 pysqlite3-binary，"
            "ChromaDB 无法使用。请执行: pip install pysqlite3-binary"
        ) from e
    sys.modules["sqlite3"] = pysqlite3
    # 替换后 ChromaDB 读取到的版本即 pysqlite3 的版本
    sqlite3 = pysqlite3  # noqa: F811
