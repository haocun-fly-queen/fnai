"""微博发布服务（阶段 5 — 微博对接）。

直接复用 E:\\发文章\\weibo_cookie_publisher.py 中已调通的核心逻辑。
只做薄封装：接参 → 调原函数 → 返回结果。
"""

import logging
import re
from pathlib import Path
from typing import Optional

# ── 直接导入已调通的微博脚本（已复制到项目内）──────────────────
from app.services.weibo_cookie_publisher import (  # type: ignore
    get_headers,
    get_xsrf_token,
    post_weibo as _sync_post_weibo,
    get_user_info as _sync_get_user_info,
    M_WEIBO_BASE,
    POST_URL,
    USER_URL,
)

logger = logging.getLogger(__name__)


# ============================================================
# 自定义异常
# ============================================================


class WeiboError(Exception):
    """微博相关错误基类。"""

    def __init__(self, message: str, code: str = "weibo_error", retryable: bool = False):
        self.message = message
        self.code = code
        self.retryable = retryable
        super().__init__(message)


class WeiboCookieExpired(WeiboError):
    """Cookie 过期。"""

    def __init__(self, message: str = "微博 Cookie 已过期，请重新配置"):
        super().__init__(message, code="cookie_expired", retryable=False)


class WeiboPublishFailed(WeiboError):
    """发布失败。"""

    def __init__(self, message: str = "微博发布失败"):
        super().__init__(message, code="publish_failed", retryable=True)


# ============================================================
# 工具函数
# ============================================================


def mask_cookie(cookie: str) -> str:
    """脱敏 Cookie，只保留前 20 个字符。"""
    if not cookie:
        return ""
    if len(cookie) <= 20:
        return cookie
    return cookie[:20] + "..."


# ============================================================
# 异步封装（FastAPI 是异步的，用 asyncio.to_thread 包装同步调用）
# ============================================================


async def verify_cookie(cookie: str) -> dict:
    """验证 Cookie 是否有效，返回用户信息。

    直接调用 weibo_cookie_publisher.py 里已调通的 get_user_info()。
    """
    import asyncio

    try:
        user = await asyncio.to_thread(_sync_get_user_info, cookie)
    except Exception as e:
        logger.error(f"验证微博 Cookie 失败: {e}")
        raise WeiboError(f"请求微博 API 失败: {e}", code="network_error", retryable=True)

    if not user or not user.get("id"):
        raise WeiboCookieExpired()

    return {
        "uid": str(user.get("id", "")),
        "screen_name": user.get("screen_name", ""),
        "avatar": user.get("profile_image_url", ""),
        "followers_count": user.get("followers_count", 0),
        "statuses_count": user.get("statuses_count", 0),
    }


async def publish_weibo(
    cookie: str,
    content: str,
    image_url: Optional[str] = None,
) -> dict:
    """发布一条微博。

    直接调用 weibo_cookie_publisher.py 里已调通的 post_weibo()。
    如果 image_url 是网络图片，先下载到临时文件再上传。
    """
    import asyncio
    import tempfile

    image_path = None
    temp_file = None

    # 如果是网络图片，先下载
    if image_url and image_url.startswith("http"):
        try:
            import httpx

            async with httpx.AsyncClient(timeout=15.0) as client:
                img_resp = await client.get(image_url)
                if img_resp.status_code == 200:
                    temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                    temp_file.write(img_resp.content)
                    temp_file.close()
                    image_path = temp_file.name
                else:
                    logger.warning(f"下载配图失败: {image_url}，将不带图发布")
        except Exception as e:
            logger.warning(f"下载配图异常: {e}，将不带图发布")

    try:
        result = await asyncio.to_thread(
            _sync_post_weibo, cookie, content, image_path
        )
    except Exception as e:
        logger.error(f"发布微博异常: {e}")
        raise WeiboPublishFailed(f"发布微博异常: {e}")
    finally:
        # 清理临时文件
        if temp_file:
            try:
                Path(temp_file.name).unlink(missing_ok=True)
            except Exception:
                pass

    if not result or "id" not in result:
        raise WeiboPublishFailed("微博发布失败，返回数据无微博 ID")

    weibo_id = str(result.get("id", ""))
    weibo_url = f"https://m.weibo.cn/detail/{weibo_id}" if weibo_id else None

    logger.info(f"微博发布成功: id={weibo_id}")
    return {
        "weibo_id": weibo_id,
        "weibo_url": weibo_url,
    }
