"""
LLM 多模型路由层

支持 DeepSeek / Kimi / Ark 多模型切换与自动降级。
所有 provider 均兼容 OpenAI SDK 接口格式。
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import AsyncOpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class LLMMessage:
    """对话消息"""

    role: str  # "system" | "user" | "assistant"
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class LLMUsage:
    """Token 用量统计"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResponse:
    """LLM 调用响应"""

    content: str
    model: str
    provider: str
    usage: Optional[LLMUsage] = None
    finish_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Provider 配置
# ---------------------------------------------------------------------------

PROVIDER_CONFIGS = {
    "deepseek": {
        "api_key": lambda: settings.DEEPSEEK_API_KEY,
        "base_url": settings.DEEPSEEK_BASE_URL,
        "model": settings.DEEPSEEK_MODEL,
    },
    "kimi": {
        "api_key": lambda: settings.KIMI_API_KEY,
        "base_url": settings.KIMI_BASE_URL,
        "model": settings.KIMI_MODEL,
    },
    "ark": {
        "api_key": lambda: settings.ARK_API_KEY,
        "base_url": settings.ARK_BASE_URL,
        "model": settings.ARK_MODEL,
    },
}


def _get_provider_names() -> List[str]:
    """获取可用 provider 列表（已配置 API Key 的）"""
    available = []
    for name, cfg in PROVIDER_CONFIGS.items():
        if cfg["api_key"]():
            available.append(name)
    return available


def _build_fallback_chain(default_provider: str) -> List[str]:
    """
    构建降级链：默认 provider -> 配置的降级列表 -> 其他可用 provider。
    去重且保持顺序。
    """
    chain = [default_provider]
    # 加入配置的降级列表
    fallback_str = settings.LLM_FALLBACK_PROVIDERS
    if fallback_str:
        for name in fallback_str.split(","):
            name = name.strip()
            if name and name not in chain:
                chain.append(name)
    # 加入其余可用 provider
    for name in _get_provider_names():
        if name not in chain:
            chain.append(name)
    return chain


# ---------------------------------------------------------------------------
# LLMProvider
# ---------------------------------------------------------------------------


class LLMProvider:
    """
    多模型 LLM 调用封装

    特性：
    - 支持 DeepSeek / Kimi / Ark 多模型切换
    - 自动降级：当前 provider 失败时按降级链尝试下一个
    - 指数退避重试
    - 流式与非流式调用
    """

    def __init__(self, provider: Optional[str] = None) -> None:
        """
        初始化 LLMProvider

        Args:
            provider: 指定 provider 名称（deepseek/kimi/ark），
                      None 则使用默认配置
        """
        self._provider = provider or settings.LLM_DEFAULT_PROVIDER
        self._fallback_chain = _build_fallback_chain(self._provider)
        self._clients: Dict[str, AsyncOpenAI] = {}

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_client(self, provider: str) -> Optional[AsyncOpenAI]:
        """获取或创建指定 provider 的 AsyncOpenAI 客户端"""
        cfg = PROVIDER_CONFIGS.get(provider)
        if not cfg:
            return None
        api_key = cfg["api_key"]()
        if not api_key:
            return None
        if provider not in self._clients:
            self._clients[provider] = AsyncOpenAI(
                api_key=api_key,
                base_url=cfg["base_url"],
                timeout=settings.LLM_REQUEST_TIMEOUT,
            )
        return self._clients[provider]

    def _get_model(self, provider: str) -> str:
        """获取 provider 对应的模型名"""
        cfg = PROVIDER_CONFIGS.get(provider, {})
        return cfg.get("model", "gpt-3.5-turbo")

    async def _call_with_retry(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        stream: bool = False,
        **kwargs: Any,
    ):
        """
        调用 LLM API，带指数退避重试。

        Returns:
            (response, client, provider) 或 (stream, client, provider)
        """
        client = self._get_client(provider)
        if not client:
            raise ValueError(f"Provider '{provider}' 未配置 API Key 或不存在")

        model = self._get_model(provider)
        max_retries = settings.LLM_MAX_RETRIES
        base_delay = settings.LLM_RETRY_BASE_DELAY
        backoff = settings.LLM_RETRY_BACKOFF

        last_error: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=kwargs.get("temperature", settings.LLM_TEMPERATURE),
                    max_tokens=kwargs.get("max_tokens", settings.LLM_MAX_TOKENS),
                    stream=stream,
                )
                return response, client, provider
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = base_delay * (backoff ** (attempt - 1))
                    logger.warning(
                        "[%s] 第 %d/%d 次调用失败: %s，%0.1fs 后重试",
                        provider,
                        attempt,
                        max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "[%s] 重试 %d 次后仍失败: %s", provider, max_retries, e
                    )

        raise last_error  # type: ignore[misc]

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        """
        非流式对话，支持自动降级。

        Args:
            messages: 对话消息列表 [{"role": "user", "content": "..."}]
            provider: 指定 provider，None 则使用默认 + 降级链
            temperature: 温度参数，None 使用默认配置
            max_tokens: 最大输出 token，None 使用默认配置

        Returns:
            LLMResponse 包含回复内容、模型、provider、用量信息
        """
        chain = [provider] if provider else self._fallback_chain

        last_error: Optional[Exception] = None
        for name in chain:
            try:
                resp, _, used_provider = await self._call_with_retry(
                    provider=name,
                    messages=messages,
                    stream=False,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                choice = resp.choices[0]
                usage = None
                if resp.usage:
                    usage = LLMUsage(
                        prompt_tokens=resp.usage.prompt_tokens,
                        completion_tokens=resp.usage.completion_tokens,
                        total_tokens=resp.usage.total_tokens,
                    )
                return LLMResponse(
                    content=choice.message.content or "",
                    model=resp.model,
                    provider=used_provider,
                    usage=usage,
                    finish_reason=choice.finish_reason,
                )
            except Exception as e:
                last_error = e
                logger.warning("[%s] 调用失败，尝试降级: %s", name, e)
                continue

        raise RuntimeError(
            f"所有 provider 调用均失败，降级链: {chain}"
        ) from last_error

    async def chat_stream(
        self,
        messages: List[Dict[str, str]],
        provider: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> AsyncGenerator[str, None]:
        """
        流式对话，逐 token 产出。

        Yields:
            str: 每个增量 token 的文本内容
        """
        chain = [provider] if provider else self._fallback_chain

        last_error: Optional[Exception] = None
        for name in chain:
            try:
                stream, _, _ = await self._call_with_retry(
                    provider=name,
                    messages=messages,
                    stream=True,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield delta.content
                return  # 成功，退出
            except Exception as e:
                last_error = e
                logger.warning("[%s] 流式调用失败，尝试降级: %s", name, e)
                continue

        raise RuntimeError(
            f"所有 provider 流式调用均失败，降级链: {chain}"
        ) from last_error

    @property
    def provider(self) -> str:
        """当前默认 provider"""
        return self._provider

    @property
    def fallback_chain(self) -> List[str]:
        """当前降级链"""
        return list(self._fallback_chain)

    @classmethod
    def available_providers(cls) -> List[str]:
        """返回所有已配置 API Key 的 provider 列表"""
        return _get_provider_names()

    @classmethod
    def get_provider_config(cls, name: str) -> Optional[Dict[str, Any]]:
        """获取指定 provider 的配置信息（不含 API Key）"""
        cfg = PROVIDER_CONFIGS.get(name)
        if not cfg:
            return None
        return {
            "name": name,
            "base_url": cfg["base_url"],
            "model": cfg["model"],
            "configured": cfg["api_key"]() is not None,
        }


# ---------------------------------------------------------------------------
# 模块级便捷实例
# ---------------------------------------------------------------------------

# 默认 provider 实例，供 CLI 工具等场景直接 import 使用
llm_provider = LLMProvider()