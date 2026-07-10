"""微信公众号发布插件（阶段 2A — 插件化重构）。

从 wechat_mp.py 的 WechatMpClient + wechat_mp.py endpoint 提取。
"""

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.wechat_mp import WechatMpClient, WechatMpError

from .base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class WechatMpPublisher(BasePublisher):
    """微信公众号发布插件。"""

    async def validate_config(self, config: dict) -> None:
        """验证微信公众号配置。"""
        required = ["app_id", "app_secret"]
        missing = [k for k in required if k not in config or not config[k]]
        if missing:
            raise ValueError(f"微信公众号配置缺少字段: {', '.join(missing)}")

    async def publish(
        self,
        article: Any,
        config: dict,
        options: dict | None = None,
        *,
        db: AsyncSession | None = None,
    ) -> PublishResult:
        """发布文章到微信公众号。

        流程：获取 token → 处理图片 → 创建草稿 → 提交发布。
        """
        if db is None:
            return PublishResult(success=False, message="微信发布需要数据库会话")

        opts = options or {}
        app_id = config.get("app_id", "")
        app_secret = config.get("app_secret", "")

        if not app_id or not app_secret:
            return PublishResult(success=False, message="微信配置缺少 app_id 或 app_secret")

        try:
            client = WechatMpClient(db=db, app_id=app_id, app_secret=app_secret)
            result = await client.publish_article(
                title=article.title or "未命名文章",
                content=article.content,
                author=opts.get("author", ""),
                digest=opts.get("digest", ""),
                thumb_media_id=opts.get("thumb_media_id"),
                config_thumb_media_id=config.get("thumb_media_id"),
                need_open_comment=opts.get("need_open_comment", True),
                only_fans_can_comment=opts.get("only_fans_can_comment", False),
            )

            return PublishResult(
                success=True,
                remote_id=result.get("publish_id", ""),
                message="微信发布成功（异步审核中）",
                metadata={
                    "draft_media_id": result.get("draft_media_id"),
                    "images_processed": result.get("images_processed", 0),
                    "images_succeeded": result.get("images_succeeded", 0),
                },
            )
        except WechatMpError as e:
            logger.error(f"微信发布失败: {e}", exc_info=True)
            return PublishResult(
                success=False,
                message=f"微信发布失败: {e.message}",
                metadata={"wx_errcode": e.wx_errcode, "retryable": e.retryable},
            )
        except Exception as e:
            logger.error(f"微信发布异常: {e}", exc_info=True)
            return PublishResult(success=False, message=f"微信发布异常: {e}")

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "app_id": {
                    "type": "string",
                    "title": "AppID",
                    "description": "微信公众号后台 → 开发 → 基本配置",
                },
                "app_secret": {
                    "type": "string",
                    "title": "AppSecret",
                    "format": "password",
                },
                "thumb_media_id": {
                    "type": "string",
                    "title": "默认封面图素材 ID",
                    "description": "可选，不填则使用系统默认封面",
                },
            },
            "required": ["app_id", "app_secret"],
        }

    def get_publish_options_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "author": {
                    "type": "string",
                    "title": "作者",
                    "description": "可选，显示在文章底部",
                },
                "digest": {
                    "type": "string",
                    "title": "摘要",
                    "description": "可选，最多 120 字",
                },
                "need_open_comment": {
                    "type": "boolean",
                    "title": "打开评论",
                    "default": True,
                },
                "only_fans_can_comment": {
                    "type": "boolean",
                    "title": "仅粉丝可评论",
                    "default": False,
                },
            },
        }
