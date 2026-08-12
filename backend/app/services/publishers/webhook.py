"""Webhook 发布插件（阶段 2A — 插件化重构）。

从 publish.py 的 _publish_to_webhook / _validate_publish_target_config 提取。
"""

import logging
from typing import Any

import httpx

from app.core.url_validator import URLValidationError, validate_webhook_url

from .base import BasePublisher, PublishResult

logger = logging.getLogger(__name__)


class WebhookPublisher(BasePublisher):
    """自定义 Webhook 发布插件。"""

    async def validate_config(self, config: dict) -> None:
        """验证 Webhook 配置。

        检查 webhook_url 存在 + URL 安全性（防 SSRF）。
        """
        if "webhook_url" not in config or not config["webhook_url"]:
            raise ValueError("Webhook 配置缺少 webhook_url")

        try:
            validate_webhook_url(config["webhook_url"])
        except URLValidationError as e:
            raise ValueError(f"Webhook URL 不安全: {e.message}")

    async def publish(
        self,
        article: Any,
        config: dict,
        options: dict | None = None,
    ) -> PublishResult:
        """发布文章到自定义 Webhook。

        发送 JSON payload（title / content / summary）到配置的 URL。
        安全特性：再次验证 webhook_url（防止配置被篡改或绕过验证）。
        """
        webhook_url = config.get("webhook_url")
        if not webhook_url:
            return PublishResult(success=False, message="Webhook 配置缺少 webhook_url")

        # 双重保险：再次验证 URL 安全性
        try:
            webhook_url = validate_webhook_url(webhook_url)
        except URLValidationError as e:
            return PublishResult(success=False, message=f"Webhook URL 不安全: {e.message}")

        headers = config.get("headers", {})

        # 获取摘要（从 seo_meta）
        summary = ""
        if article.seo_meta and isinstance(article.seo_meta, dict):
            summary = article.seo_meta.get("description", "")

        payload = {
            "title": article.title,
            "content": article.content,
            "summary": summary,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(webhook_url, json=payload, headers=headers)
                response.raise_for_status()
                return PublishResult(
                    success=True,
                    remote_id=response.text[:200],
                    message="Webhook 调用成功",
                )
        except httpx.HTTPStatusError as e:
            logger.error(f"Webhook HTTP 错误: {e}", exc_info=True)
            return PublishResult(
                success=False,
                message=f"Webhook 返回错误: {e.response.status_code}",
            )
        except Exception as e:
            logger.error(f"Webhook 发布失败: {e}", exc_info=True)
            return PublishResult(success=False, message=f"Webhook 发布失败: {e}")

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "webhook_url": {
                    "type": "string",
                    "title": "Webhook URL",
                    "description": "接收文章数据的 HTTP 端点",
                    "format": "uri",
                },
                "headers": {
                    "type": "object",
                    "title": "自定义请求头",
                    "description": "可选，如 Authorization 等",
                    "additionalProperties": {"type": "string"},
                },
            },
            "required": ["webhook_url"],
        }

    def get_publish_options_schema(self) -> dict:
        return {"type": "object", "properties": {}}
