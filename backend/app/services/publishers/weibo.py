"""微博发布插件（阶段 2A — 插件化重构）。

从 weibo.py + weibo.py endpoint 提取。
"""

import logging
import re
from typing import Any

from app.services.weibo import (
    WeiboCookieExpired,
    WeiboError,
    WeiboPublishFailed,
    publish_weibo,
)

from .base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class WeiboPublisher(BasePublisher):
    """微博发布插件（Cookie 方式）。"""

    async def validate_config(self, config: dict) -> None:
        """验证微博配置。"""
        if "cookie" not in config or not config["cookie"]:
            raise ValueError("微博配置缺少 cookie")

    async def publish(
        self,
        article: Any,
        config: dict,
        options: dict | None = None,
    ) -> PublishResult:
        """发布文章到微博。

        流程：构造内容（标题 + 正文摘要）→ 调用移动端 API 发布。
        """
        opts = options or {}
        cookie = config.get("cookie", "")
        if not cookie:
            return PublishResult(success=False, message="微博 Cookie 为空，请重新配置")

        # 构造微博内容
        content = opts.get("content", "")
        if not content:
            # 默认取文章标题 + 正文（去除 HTML 标签）
            text = re.sub(r"<[^>]+>", "", article.content)
            text = re.sub(r"\s+", " ", text).strip()
            max_content_len = 1800
            if len(text) > max_content_len:
                text = text[:max_content_len] + "..."
            content = f"{article.title}\n\n{text}"

        # 追加尾部内容（话题标签等）
        suffix = opts.get("suffix") or config.get("default_suffix", "")
        if suffix:
            content = f"{content}\n\n{suffix}"

        try:
            weibo_result = await publish_weibo(
                cookie=cookie,
                content=content,
                image_url=opts.get("image_url"),
            )
            return PublishResult(
                success=True,
                remote_id=weibo_result.get("weibo_id", ""),
                message="微博发布成功",
                metadata={
                    "weibo_url": weibo_result.get("weibo_url"),
                },
            )
        except WeiboCookieExpired as e:
            return PublishResult(success=False, message=e.message)
        except WeiboPublishFailed as e:
            return PublishResult(success=False, message=e.message)
        except WeiboError as e:
            return PublishResult(success=False, message=e.message)
        except Exception as e:
            logger.error(f"微博发布异常: {e}", exc_info=True)
            return PublishResult(success=False, message=f"微博发布异常: {e}")

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "cookie": {
                    "type": "string",
                    "title": "微博 Cookie",
                    "description": "从浏览器 F12 → Network → 复制 Cookie 请求头",
                    "format": "password",
                },
                "default_suffix": {
                    "type": "string",
                    "title": "默认尾部内容",
                    "description": "可选，每条微博末尾自动追加（如话题标签 #xxx#）",
                },
            },
            "required": ["cookie"],
        }

    def get_publish_options_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "title": "自定义内容",
                    "description": "可选，不填则自动生成（标题 + 正文摘要）",
                },
                "suffix": {
                    "type": "string",
                    "title": "尾部内容",
                    "description": "可选，覆盖配置中的默认尾部",
                },
                "image_url": {
                    "type": "string",
                    "title": "配图 URL",
                    "description": "可选，网络图片地址",
                },
            },
        }
