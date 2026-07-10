"""WordPress 发布插件（阶段 2A — 插件化重构）。

从 publish.py 的 _publish_to_wordpress / _validate_publish_target_config 提取。
"""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config_crypto import decrypt_config
from app.core.url_validator import URLValidationError, validate_wordpress_url
from app.models.publish_log import PublishLog, PublishStatus
from app.services.wordpress import WordPressClient

from .base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class WordPressPublisher(BasePublisher):
    """WordPress REST API 发布插件。"""

    async def validate_config(self, config: dict) -> None:
        """验证 WordPress 配置。

        检查必填字段 + URL 安全性（防 SSRF）。
        """
        required = ["site_url", "username", "app_password"]
        missing = [k for k in required if k not in config or not config[k]]
        if missing:
            raise ValueError(f"WordPress 配置缺少字段: {', '.join(missing)}")

        try:
            validate_wordpress_url(config["site_url"])
        except URLValidationError as e:
            raise ValueError(f"WordPress URL 不安全: {e.message}")

    async def publish(
        self,
        article: Any,
        config: dict,
        options: dict | None = None,
        *,
        db: AsyncSession | None = None,
        target_id: UUID | None = None,
    ) -> PublishResult:
        """发布文章到 WordPress。

        支持更新：如果该文章已发布到同一目标（有成功的 remote_id），则更新远程文章。
        """
        opts = options or {}
        status = opts.get("status", "draft")

        required_keys = ["site_url", "username", "app_password"]
        missing = [k for k in required_keys if k not in config]
        if missing:
            return PublishResult(
                success=False,
                message=f"WordPress 配置缺少字段: {', '.join(missing)}",
            )

        client = WordPressClient(
            site_url=config["site_url"],
            username=config["username"],
            app_password=config["app_password"],
        )

        # 查询是否已发布到同一目标（需要更新而非新建）
        action = "created"
        remote_id = None
        if db and target_id:
            existing_stmt = (
                select(PublishLog)
                .where(
                    PublishLog.article_id == article.id,
                    PublishLog.target_id == target_id,
                    PublishLog.status == PublishStatus.SUCCESS,
                    PublishLog.remote_id.isnot(None),
                )
                .order_by(PublishLog.published_at.desc())
                .limit(1)
            )
            result = await db.execute(existing_stmt)
            prev_log = result.scalars().first()

            if prev_log and prev_log.remote_id:
                try:
                    post_id = await client.update_post(
                        post_id=int(prev_log.remote_id),
                        title=article.title or "未命名文章",
                        content=article.content,
                        status=status,
                    )
                    return PublishResult(
                        success=True,
                        remote_id=str(post_id),
                        message="更新成功",
                        metadata={"action": "updated"},
                    )
                except Exception as e:
                    logger.warning(f"WordPress 更新失败，尝试新建: {e}")
                    # 更新失败 → 降级为新建

        # 首次发布 → 创建新文章
        try:
            post_id = await client.create_post(
                title=article.title or "未命名文章",
                content=article.content,
                status=status,
            )
            return PublishResult(
                success=True,
                remote_id=str(post_id),
                message="发布成功",
                metadata={"action": "created"},
            )
        except Exception as e:
            logger.error(f"WordPress 发布失败: {e}", exc_info=True)
            return PublishResult(
                success=False,
                message=f"WordPress 发布失败: {e}",
            )

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "site_url": {
                    "type": "string",
                    "title": "站点 URL",
                    "description": "WordPress 站点地址，如 https://example.com",
                    "format": "uri",
                },
                "username": {
                    "type": "string",
                    "title": "用户名",
                },
                "app_password": {
                    "type": "string",
                    "title": "应用密码",
                    "description": "WordPress 后台 → 用户 → Application Passwords 生成",
                    "format": "password",
                },
            },
            "required": ["site_url", "username", "app_password"],
        }

    def get_publish_options_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "title": "发布状态",
                    "enum": ["draft", "publish", "pending"],
                    "default": "draft",
                },
            },
        }
