"""LLM chat 调用客户端（阶段 4 Step 3）。

职责：
    - 封装 OpenAI 兼容 chat completion 接口（实际接千问 qwen-plus）
    - 每次调用自动写 ModelCallLog（成本审计、排查）
    - 限流/网络抖动用 tenacity 指数退避重试

设计要点：
    - 同步函数（生成 pipeline 是 async，会用 asyncio.to_thread 调用）
    - 不直接抛 openai 的异常，统一包成 LLMError
    - prompt/response 截断到 1000 字存日志，原文不落库

跟 services/embedding.py 同款思路，只是模型从 embedding 换成 chat。
"""

import logging
import time

from openai import APIConnectionError, APITimeoutError, RateLimitError
from openai import OpenAI
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


# ============================================================
# 业务异常
# ============================================================


class LLMError(Exception):
    """LLM 调用失败。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ============================================================
# 调用结果
# ============================================================


class LLMResult:
    """一次 chat 调用的结果（content + 用量 + 耗时）。

    用普通类不用 dataclass：字段少、用法集中，加注释也清晰。
    pipeline 拿到这个对象后会把 token/duration 等写进 ModelCallLog。
    """

    __slots__ = ("content", "model", "prompt_tokens", "completion_tokens",
                 "total_tokens", "duration_ms", "prompt_preview")

    def __init__(
        self,
        *,
        content: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        duration_ms: int,
        prompt_preview: str,
    ) -> None:
        self.content = content
        self.model = model
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens
        self.duration_ms = duration_ms
        self.prompt_preview = prompt_preview


# ============================================================
# 客户端（懒加载单例）
# ============================================================

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """懒加载 OpenAI 同步客户端。同 embedding.py 的思路。"""
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY 未配置")
        _client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=120.0,  # chat 比 embedding 慢，给宽点
        )
    return _client


# ============================================================
# 主函数
# ============================================================


def chat(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> LLMResult:
    """调一次 chat completion。

    Args:
        system_prompt: 系统消息（角色设定）
        user_prompt: 用户消息（实际任务）
        model: 模型名，默认从 settings.openai_chat_model 读（qwen-plus）
        temperature: 创意度 0-1，0=确定性最高，1=最发散
        max_tokens: 输出上限。None = 模型默认

    Returns:
        LLMResult 含 content 和用量信息

    Raises:
        LLMError: API 持续失败 / key 缺失
    """
    return _chat_with_retry(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model or settings.openai_chat_model,
        temperature=temperature,
        max_tokens=max_tokens,
    )


@retry(
    retry=retry_if_exception_type(
        (RateLimitError, APIConnectionError, APITimeoutError)
    ),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _chat_with_retry(
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int | None,
) -> LLMResult:
    """真正调 API 的内层函数（带 tenacity 自动重试 429/超时）。"""
    client = _get_client()
    start = time.monotonic()
    try:
        kwargs: dict = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        resp = client.chat.completions.create(**kwargs)
    except (RateLimitError, APIConnectionError, APITimeoutError):
        raise  # tenacity 接手重试
    except Exception as exc:
        # 鉴权 / 参数错 / 服务端 4xx：不重试，直接抛
        raise LLMError(f"chat API 调用失败: {exc}")

    duration_ms = int((time.monotonic() - start) * 1000)
    usage = resp.usage
    content = resp.choices[0].message.content or ""

    return LLMResult(
        content=content,
        model=resp.model or model,
        prompt_tokens=usage.prompt_tokens if usage else 0,
        completion_tokens=usage.completion_tokens if usage else 0,
        total_tokens=usage.total_tokens if usage else 0,
        duration_ms=duration_ms,
        prompt_preview=(system_prompt + "\n\n---\n\n" + user_prompt)[:1000],
    )
