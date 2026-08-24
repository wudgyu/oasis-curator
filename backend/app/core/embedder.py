"""
Embedding 向量化封装

主路径：智谱 embedding-2（云端 API，1024 维），配置 ZHIPU_API_KEY 后启用
备用路径：Ollama bge-m3（本地 BGE 多语言模型，1024 维），中文语义效果好
兜底路径：本地 MiniLM（ONNX 轻量模型，384 维），无 Ollama/Key 时的验证方案

选择规则（EMBEDDING_PROVIDER）：
- auto（默认）: 智谱 Key > Ollama bge-m3 > MiniLM
- zhipu / ollama / minilm: 强制指定

注意：不同模型的向量维度与语义空间不同，切换后需重建向量索引。
"""

import asyncio
import logging
from typing import List, Optional

import httpx

from app.core import _sqlite_compat  # noqa: F401  必须在 import chromadb 之前（旧系统 sqlite3 兼容）
from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Embedding 调用失败"""


# ---------------------------------------------------------------------------
# 相似度工具
# ---------------------------------------------------------------------------


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """余弦相似度：-1 ~ 1，越高越相似"""
    if len(a) != len(b):
        raise ValueError(f"向量维度不一致: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# 智谱 embedding-2（云端）
# ---------------------------------------------------------------------------


class ZhipuEmbedder:
    """智谱 embedding-2 云端向量化（OpenAI 兼容接口），指数退避重试"""

    name = "zhipu"
    dimension = 1024
    _batch_size = 8
    _max_retries = 3

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """批量向量化，按 batch 分批请求，失败指数退避重试"""
        if not texts:
            return []
        embeddings: List[List[float]] = []
        url = f"{self._base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=60) as client:
            for i in range(0, len(texts), self._batch_size):
                batch = texts[i : i + self._batch_size]
                embeddings.extend(
                    await self._embed_batch(client, url, headers, batch)
                )
        return embeddings

    async def _embed_batch(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict,
        batch: List[str],
    ) -> List[List[float]]:
        last_error: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 1):
            try:
                resp = await client.post(
                    url,
                    headers=headers,
                    json={"model": self._model, "input": batch},
                )
                resp.raise_for_status()
                data = resp.json()["data"]
                # 按 index 排序，保证与输入顺序一致
                data.sort(key=lambda d: d["index"])
                return [d["embedding"] for d in data]
            except httpx.HTTPStatusError as e:
                last_error = e
                detail = e.response.text[:200]
                if e.response.status_code < 500 and e.response.status_code != 429:
                    # 4xx（鉴权/参数错误等）重试无意义
                    raise EmbeddingError(
                        f"智谱 Embedding 调用失败（HTTP {e.response.status_code}）: {detail}"
                    ) from e
            except httpx.HTTPError as e:
                last_error = e

            if attempt < self._max_retries:
                delay = 2 ** (attempt - 1)
                logger.warning(
                    "智谱 Embedding 第 %d/%d 次失败: %s，%ds 后重试",
                    attempt,
                    self._max_retries,
                    last_error,
                    delay,
                )
                await asyncio.sleep(delay)

        raise EmbeddingError(f"智谱 Embedding 重试 {self._max_retries} 次后仍失败") from last_error


# ---------------------------------------------------------------------------
# Ollama bge-m3（本地 BGE 多语言模型）
# ---------------------------------------------------------------------------


class OllamaEmbedder:
    """
    Ollama 本地 BGE 模型向量化（bge-m3，1024 维）。

    通过 Ollama /api/embeddings 接口调用，全部推理在本机完成。
    Ollama 接口为单条文本请求，内部并发调用加速批量向量化。
    """

    name = "ollama"
    _max_concurrency = 4

    def __init__(self, host: str, model: str) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._dimension: Optional[int] = None  # 首次调用后确定
        self._semaphore = asyncio.Semaphore(self._max_concurrency)

    @property
    def dimension(self) -> Optional[int]:
        return self._dimension

    async def _embed_one(self, client: httpx.AsyncClient, text: str) -> List[float]:
        async with self._semaphore:
            resp = await client.post(
                f"{self._host}/api/embeddings",
                json={"model": self._model, "prompt": text},
            )
            resp.raise_for_status()
            vec = resp.json()["embedding"]
            if self._dimension is None:
                self._dimension = len(vec)
            return vec

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """逐条并发请求 Ollama，返回与输入同序的向量列表"""
        if not texts:
            return []
        async with httpx.AsyncClient(timeout=120) as client:
            return await asyncio.gather(
                *(self._embed_one(client, t) for t in texts)
            )


# ---------------------------------------------------------------------------
# 本地 MiniLM（无 Key 验证 / 离线场景）
# ---------------------------------------------------------------------------


class MiniLMEmbedder:
    """
    本地 MiniLM 轻量模型（Chroma 默认 ONNX 模型，384 维）。

    首次调用自动下载模型（约 80MB），之后完全本地推理。
    定位：没有智谱 Key 时的本地验证方案，语义效果弱于 embedding-2。
    """

    name = "minilm"
    dimension = 384

    def __init__(self) -> None:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        self._ef = DefaultEmbeddingFunction()

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """ONNX 推理是同步阻塞的，放入线程池避免阻塞事件循环"""
        return await asyncio.to_thread(self._ef, texts)


# ---------------------------------------------------------------------------
# 工厂与模块级实例
# ---------------------------------------------------------------------------


def _ollama_has_embed_model() -> bool:
    """探测 Ollama 是否已拉取嵌入模型（探测失败不阻塞，回退下一优先级）"""
    try:
        resp = httpx.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=2)
        if resp.status_code != 200:
            return False
        models = {m.get("name", "") for m in resp.json().get("models", [])}
        return any(
            m == settings.OLLAMA_EMBED_MODEL
            or m.startswith(settings.OLLAMA_EMBED_MODEL + ":")
            for m in models
        )
    except httpx.HTTPError:
        return False


def _resolve_provider() -> str:
    provider = settings.EMBEDDING_PROVIDER.lower()
    if provider == "auto":
        if settings.ZHIPU_API_KEY:
            return "zhipu"
        if _ollama_has_embed_model():
            return "ollama"
        return "minilm"
    if provider not in ("zhipu", "ollama", "minilm"):
        raise EmbeddingError(
            f"未知 EMBEDDING_PROVIDER: {provider}（支持 auto/zhipu/ollama/minilm）"
        )
    return provider


def get_embedder(provider: Optional[str] = None):
    """
    按配置创建 Embedder 实例。

    Args:
        provider: 强制指定 zhipu / ollama / minilm；None 或 "auto" 按 EMBEDDING_PROVIDER 解析
    """
    if provider and provider.lower() != "auto":
        name = provider.lower()
    else:
        name = _resolve_provider()
    if name == "zhipu":
        if not settings.ZHIPU_API_KEY:
            raise EmbeddingError("EMBEDDING_PROVIDER=zhipu 但未配置 ZHIPU_API_KEY")
        return ZhipuEmbedder(
            api_key=settings.ZHIPU_API_KEY,
            base_url=settings.ZHIPU_EMBEDDING_BASE_URL,
            model=settings.ZHIPU_EMBEDDING_MODEL,
        )
    if name == "ollama":
        return OllamaEmbedder(
            host=settings.OLLAMA_HOST,
            model=settings.OLLAMA_EMBED_MODEL,
        )
    if name == "minilm":
        return MiniLMEmbedder()
    raise EmbeddingError(f"未知 provider: {name}")


# 模块级实例：解析出的实际模型（auto 模式下按 智谱 > Ollama > MiniLM 优先级）
embedder = get_embedder()
logger.info("Embedding 模型: %s（维度 %s）", embedder.name, embedder.dimension)
