"""
LLM 多模型路由层

支持 DeepSeek / Kimi / Ark 多模型切换与自动降级。
所有 provider 均兼容 OpenAI SDK 接口格式。
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional

from openai import APIConnectionError, APITimeoutError, AsyncOpenAI

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
        "stream_usage": True,  # 支持流式末尾返回 usage
    },
    "kimi": {
        "api_key": lambda: settings.KIMI_API_KEY,
        "base_url": settings.KIMI_BASE_URL,
        "model": settings.KIMI_MODEL,
        "stream_usage": True,
    },
    "ark": {
        "api_key": lambda: settings.ARK_API_KEY,
        "base_url": settings.ARK_BASE_URL,
        "model": settings.ARK_MODEL,
        "stream_usage": False,  # 未确认支持，默认关闭避免参数兼容问题
    },
}

# 配额耗尽类错误关键字：命中即视为不可重试，快速降级
_QUOTA_KEYWORDS = ("quota", "balance", "billing", "额度")


def _is_retryable_error(error: Exception) -> bool:
    """
    判断错误是否值得重试。

    可重试：网络抖动（超时/连接中断）、服务端 5xx、普通限流（短暂恢复）
    不可重试：配额耗尽（数小时才重置）、鉴权失败、参数错误、上下文超限
    """
    status_code = getattr(error, "status_code", None)
    if status_code is None:
        # 无状态码的错误：超时、连接中断可重试，其余快速失败
        return isinstance(error, (APIConnectionError, APITimeoutError))
    if status_code == 429:
        # 普通限流可退避重试；配额耗尽重试无意义
        return not any(k in str(error).lower() for k in _QUOTA_KEYWORDS)
    if 500 <= status_code < 600:
        return True
    # 其余 4xx（鉴权、参数、上下文超限等）重试无意义，直接降级
    return False


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
        # 最近一次成功应答的 provider 与 Token 用量（降级后以实际应答模型为准）
        self._last_provider: Optional[str] = None
        self._last_usage: Optional[LLMUsage] = None

    def _resolve_chain(self, provider: Optional[str]) -> List[str]:
        """
        解析调用链：显式指定 provider 时其优先但仍保留降级链；
        未指定时使用默认降级链。
        """
        if not provider:
            return self._fallback_chain
        return [provider] + [p for p in self._fallback_chain if p != provider]

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
                request_params: Dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": kwargs.get("temperature", settings.LLM_TEMPERATURE),
                    "max_tokens": kwargs.get("max_tokens", settings.LLM_MAX_TOKENS),
                    "stream": stream,
                }
                # 部分模型支持在流式末尾返回 usage（需显式开启）
                if stream and PROVIDER_CONFIGS.get(provider, {}).get("stream_usage"):
                    request_params["stream_options"] = {"include_usage": True}
                response = await client.chat.completions.create(**request_params)
                return response, client, provider
            except Exception as e:
                last_error = e
                if not _is_retryable_error(e):
                    # 配额耗尽/鉴权失败/参数错误等：重试无意义，快速降级
                    logger.warning(
                        "[%s] 调用失败（不可重试类错误，直接降级）: %s", provider, e
                    )
                    raise
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
        chain = self._resolve_chain(provider)

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
                self._last_provider = used_provider
                self._last_usage = usage
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

        降级规则：
        - 首个 token 产出前失败 → 直接切换下一个 provider（输出不受影响）
        - 已产出部分 token 后失败 → 终止本次调用（切换模型会造成输出混乱）

        Yields:
            str: 每个增量 token 的文本内容
        """
        chain = self._resolve_chain(provider)

        last_error: Optional[Exception] = None
        for name in chain:
            yielded = False
            try:
                stream, _, _ = await self._call_with_retry(
                    provider=name,
                    messages=messages,
                    stream=True,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                # 流建立成功：应答模型确定为当前 provider
                self._last_provider = name
                self._last_usage = None
                async for chunk in stream:
                    # 部分模型在最后一个 chunk 返回 usage
                    if chunk.usage:
                        self._last_usage = LLMUsage(
                            prompt_tokens=chunk.usage.prompt_tokens,
                            completion_tokens=chunk.usage.completion_tokens,
                            total_tokens=chunk.usage.total_tokens,
                        )
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        yielded = True
                        yield delta.content
                return  # 成功，退出
            except Exception as e:
                last_error = e
                if yielded:
                    # 已输出部分内容，切换模型会造成输出混乱，直接终止
                    logger.error("[%s] 流式输出中途失败，终止本次调用: %s", name, e)
                    raise
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
    def last_provider(self) -> Optional[str]:
        """最近一次成功应答的 provider（降级后为实际应答的模型）"""
        return self._last_provider

    @property
    def last_usage(self) -> Optional[LLMUsage]:
        """最近一次成功应答的 Token 用量（流式响应未返回 usage 时为 None）"""
        return self._last_usage

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