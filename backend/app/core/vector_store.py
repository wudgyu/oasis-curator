"""
向量库封装（ChromaDB 服务端模式）

- 连接 Docker 中的 ChromaDB（HttpClient），命名空间 tenant=curator / database=oasis
- 单 collection 存储所有文档 chunk，元数据携带 tenant_id / doc_id 实现多租户隔离
- 检索时强制 where={"tenant_id": ...} 过滤：租户 A 的文档永不会被租户 B 检索到
- collection 使用余弦距离空间，score = 1 - distance（0~1，越大越相关）

前置：运行 scripts/init_chroma.py 初始化服务端命名空间。
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from app.core import _sqlite_compat  # noqa: F401  必须在 import chromadb 之前
from app.core.chunker import Chunk
from app.core.config import settings

import chromadb

logger = logging.getLogger(__name__)

COLLECTION_NAME = "documents"


@dataclass
class SearchResult:
    """检索命中的文本块"""

    text: str
    score: float  # 余弦相似度（0~1）
    source_file: str
    chunk_index: int
    page: Optional[int]
    doc_id: str
    tenant_id: str

    @property
    def citation(self) -> str:
        """引用标注：[来源: 文件名, 第N段]"""
        return f"[来源: {self.source_file}, 第{self.chunk_index + 1}段]"


class VectorStore:
    """
    ChromaDB 封装：写入 / 检索 / 删除

    所有操作按 tenant_id 过滤，多租户隔离在本层强制执行，
    即使上层传错租户参数也无法越权读取其他租户的向量。
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        tenant: Optional[str] = None,
        database: Optional[str] = None,
    ) -> None:
        host = host or settings.CHROMA_HOST
        port = port or settings.CHROMA_PORT
        tenant = tenant or settings.CHROMA_TENANT
        database = database or settings.CHROMA_DATABASE

        self._client = chromadb.HttpClient(
            host=host, port=port, tenant=tenant, database=database
        )
        self._collection = self._client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},  # 余弦距离：score = 1 - distance
        )
        logger.info(
            "向量库已连接: %s:%s (tenant=%s, database=%s, collection=%s)",
            host,
            port,
            tenant,
            database,
            COLLECTION_NAME,
        )

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def add_chunks(
        self,
        chunks: List[Chunk],
        embeddings: List[List[float]],
        doc_id: str,
        tenant_id: str,
    ) -> None:
        """
        批量写入 chunk 向量 + 元数据。

        Args:
            chunks: 切分结果
            embeddings: 与 chunks 一一对应的向量
            doc_id: 文档 ID（业务表 documents.id）
            tenant_id: 所属租户（检索时的隔离依据）
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks({len(chunks)}) 与 embeddings({len(embeddings)}) 数量不一致"
            )
        if not chunks:
            return

        try:
            self._collection.add(
                ids=[f"{doc_id}:{c.chunk_index}" for c in chunks],
                embeddings=embeddings,
                documents=[c.text for c in chunks],
                metadatas=[self._build_metadata(c, doc_id, tenant_id) for c in chunks],
            )
        except Exception as e:
            # 维度不匹配：Embedding 模型已切换（如 MiniLM 384 → bge-m3 1024）
            if "dimension" in str(e).lower():
                current_dim = self._collection_dimension()
                raise ValueError(
                    f"向量维度不匹配（集合为 {current_dim} 维，本次为 {len(embeddings[0])} 维）。"
                    f"已切换 Embedding 模型？需重建向量索引（python scripts/reset_chroma.py --yes）"
                    f"后重新上传全部文档。"
                ) from e
            raise
        logger.info("向量入库: doc=%s, %d chunks", doc_id, len(chunks))

    def _collection_dimension(self) -> int:
        """取集合当前向量维度（空集合返回 0）"""
        res = self._collection.get(limit=1, include=["embeddings"])
        if res.get("embeddings"):
            return len(res["embeddings"][0])
        return 0

    @staticmethod
    def _build_metadata(chunk: Chunk, doc_id: str, tenant_id: str) -> dict:
        """Chroma 元数据不允许 None 值，page 按需写入"""
        meta = {
            "tenant_id": tenant_id,
            "doc_id": doc_id,
            "source_file": chunk.source_file,
            "chunk_index": chunk.chunk_index,
            "strategy": chunk.strategy,
        }
        if chunk.page is not None:
            meta["page"] = chunk.page
        return meta

    # ------------------------------------------------------------------
    # 检索
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: List[float],
        tenant_id: str,
        top_k: int = 5,
        doc_id: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        语义检索 Top-K，强制按租户过滤（可再限定单文档）。

        Args:
            query_embedding: 问题向量
            tenant_id: 租户过滤条件（必传）
            top_k: 返回条数
            doc_id: 可选，限定在指定文档内检索

        Returns:
            按相似度降序的命中列表
        """
        # Chroma 多条件过滤需用 $and 包裹（单条件直接平铺）
        where: dict = {"tenant_id": tenant_id}
        if doc_id:
            where = {"$and": [{"tenant_id": tenant_id}, {"doc_id": doc_id}]}

        res = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        results: List[SearchResult] = []
        docs = res.get("documents") or [[]]
        metas = res.get("metadatas") or [[]]
        distances = res.get("distances") or [[]]
        for text, meta, distance in zip(docs[0], metas[0], distances[0]):
            if meta is None:
                continue
            results.append(
                SearchResult(
                    text=text or "",
                    score=round(1 - distance, 4),  # 余弦距离 → 相似度
                    source_file=meta["source_file"],
                    chunk_index=meta["chunk_index"],
                    page=meta.get("page"),
                    doc_id=meta["doc_id"],
                    tenant_id=meta["tenant_id"],
                )
            )
        return results

    # ------------------------------------------------------------------
    # 删除 / 统计
    # ------------------------------------------------------------------

    def delete_document(self, doc_id: str, tenant_id: str) -> int:
        """删除指定文档的全部向量，返回删除条数"""
        where = {"$and": [{"doc_id": doc_id}, {"tenant_id": tenant_id}]}
        existing = self._collection.get(where=where)
        count = len(existing.get("ids", []))
        if count:
            self._collection.delete(where=where)
        logger.info("向量删除: doc=%s, %d chunks", doc_id, count)
        return count

    def count(self, tenant_id: Optional[str] = None) -> int:
        """统计向量条数（可按租户过滤）"""
        if tenant_id:
            res = self._collection.get(where={"tenant_id": tenant_id})
            return len(res.get("ids", []))
        return self._collection.count()


# 模块级实例：供 API 与脚本直接使用
vector_store = VectorStore()
