# 概念：文本向量化（Embedding）
#   把一段文本变成一个定长浮点数组（这里 1536 维），让"语义相近的文本"在向量空间里
#   距离也相近。检索时用查询向量去比对 chunk 向量，找最相似的段落。
#   Java 对照：≈ 调一个远程 REST API，传 String[] 返回 float[][]。
#
# 模块：backend/app/services/embedding.py，service 层。
#   被 workers/tasks.py 调用（在 chunker 之后、写 DB 之前）。
#   走 OpenAI 兼容接口——这里实际接的是阿里千问 DashScope（base_url 指向 compatible-mode）。
#
# 作用：
#   输入：list[str]（一批 chunk 文本）
#   输出：list[list[float]]（一一对应的向量，维度 = settings.embedding_dim）
#   不干什么：不切分、不碰 DB。
#
# 怎么写：
#   - 用 OpenAI 同步客户端（worker 是同步进程，不掺 async，避免事件循环坑）。
#   - 分小批调用：千问兼容接口单次 input 条数有上限（v2 ≈ 25），用 _BATCH_SIZE 控制。
#   - 限流/网络抖动：用 tenacity 对 429/5xx/超时做指数退避重试，最多 3 次。
#   - 维度自检：首次返回时校验维度 == embedding_dim，对不上立刻抛错（防脏数据入库）。
#   - 陷阱：返回顺序——OpenAI 接口保证 data 按 index 排序，这里仍显式按 index 排一次，
#     绝不依赖"恰好有序"。

import logging

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

# 单次请求最多送多少条文本（千问兼容接口的保守上限）
_BATCH_SIZE = 20


# ============================================================
# 业务异常
# ============================================================


class EmbeddingError(Exception):
    """向量化失败。上层（tasks）catch 后把 document.status 置 FAILED。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ============================================================
# 客户端（懒加载单例）
# ============================================================

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """懒加载 OpenAI 同步客户端。

    懒加载原因：import 时不连网；key 缺失的报错延迟到真正调用时，
    更容易定位（而不是模块导入就炸）。
    """
    global _client
    if _client is None:
        if not settings.openai_api_key:
            raise EmbeddingError(
                "OPENAI_API_KEY 未配置，无法调用 embedding 接口"
            )
        _client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=60.0,
        )
    return _client


# ============================================================
# 主函数
# ============================================================


def embed_texts(texts: list[str]) -> list[list[float]]:
    """把一批文本向量化。

    Args:
        texts: 文本列表

    Returns:
        向量列表，与输入一一对应，每个向量维度 = settings.embedding_dim

    Raises:
        EmbeddingError: key 缺失 / API 持续失败 / 维度不匹配
    """
    if not texts:
        return []

    vectors: list[list[float]] = []
    # 分批，避免单次请求条数超限
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        vectors.extend(_embed_batch(batch))

    # 维度自检（用第一个向量代表）
    dim = len(vectors[0])
    if dim != settings.embedding_dim:
        raise EmbeddingError(
            f"embedding 维度不匹配：模型返回 {dim}，"
            f"但配置/表结构是 {settings.embedding_dim}。"
            f"请检查 OPENAI_EMBEDDING_MODEL 或 embedding_dim 设置。"
        )

    logger.info("embed done: count=%d dim=%d", len(vectors), dim)
    return vectors


@retry(
    retry=retry_if_exception_type(
        (RateLimitError, APIConnectionError, APITimeoutError)
    ),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _embed_batch(batch: list[str]) -> list[list[float]]:
    """调一次 API 把一小批文本向量化（带指数退避重试）。

    tenacity 装饰器：遇到限流(429)/连接错/超时，2s→4s→... 退避重试，最多 3 次。
    其他错误（如鉴权 401、参数错）不重试，直接冒泡。
    """
    client = _get_client()
    try:
        resp = client.embeddings.create(
            model=settings.openai_embedding_model,
            input=batch,
        )
    except (RateLimitError, APIConnectionError, APITimeoutError):
        # 交给 tenacity 重试
        raise
    except Exception as exc:
        # 不可重试的错误（鉴权/参数/服务端 4xx）→ 包成业务异常
        raise EmbeddingError(f"embedding API 调用失败: {exc}")

    # 显式按 index 排序，不依赖返回顺序
    ordered = sorted(resp.data, key=lambda d: d.index)
    return [d.embedding for d in ordered]
