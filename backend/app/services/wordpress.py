"""WordPress REST API 客户端（阶段 5）—— 一键发布到 WordPress。

WordPress REST API v2 文档：https://developer.wordpress.org/rest-api/reference/posts/

认证方式：Application Password（WordPress 5.6+）
https://make.wordpress.org/core/2020/11/05/application-passwords-integration-guide/

安全特性：
    - URL 验证，防止 SSRF 攻击（不允许内网地址）
"""

import logging
from typing import Any

import httpx

from app.core.url_validator import URLValidationError, validate_wordpress_url

logger = logging.getLogger(__name__)


class WordPressClient:
    """WordPress REST API 客户端（基于 Application Password 认证）。

    使用方法：
        client = WordPressClient(
            site_url="https://example.com",
            username="admin",
            app_password="xxxx xxxx xxxx xxxx xxxx xxxx"
        )
        post_id = await client.create_post(title="标题", content="<p>正文</p>", status="draft")
    """

    def __init__(self, site_url: str, username: str, app_password: str):
        """初始化客户端。

        Args:
            site_url: WordPress 站点 URL（如 https://example.com，不要带 /wp-json）
            username: WordPress 用户名
            app_password: Application Password（格式：xxxx xxxx xxxx xxxx，空格会自动去除）

        Raises:
            URLValidationError: URL 不安全（内网地址、无效格式等）
        """
        # 验证 URL 安全性（防止 SSRF）
        validated_url = validate_wordpress_url(site_url.rstrip("/"))

        self.site_url = validated_url
        self.api_base = f"{self.site_url}/wp-json/wp/v2"
        self.username = username
        self.app_password = app_password.replace(" ", "")  # 去除空格

    async def create_post(
        self,
        title: str,
        content: str,
        status: str = "draft",
        excerpt: str = "",
        categories: list[int] | None = None,
        tags: list[int] | None = None,
    ) -> int:
        """创建文章（WordPress Post）。

        Args:
            title: 文章标题
            content: 文章正文（HTML 格式）
            status: draft / publish / pending
            excerpt: 摘要
            categories: 分类 ID 列表
            tags: 标签 ID 列表

        Returns:
            WordPress post_id

        Raises:
            httpx.HTTPStatusError: API 调用失败
        """
        url = f"{self.api_base}/posts"
        payload: dict[str, Any] = {
            "title": title,
            "content": content,
            "status": status,
            "excerpt": excerpt,
        }

        if categories:
            payload["categories"] = categories
        if tags:
            payload["tags"] = tags

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                auth=(self.username, self.app_password),
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"WordPress post created: {data['id']} - {data['link']}")
            return data["id"]

    async def update_post(
        self,
        post_id: int,
        title: str | None = None,
        content: str | None = None,
        status: str | None = None,
        excerpt: str | None = None,
        categories: list[int] | None = None,
        tags: list[int] | None = None,
    ) -> int:
        """更新已存在的文章。

        Args:
            post_id: WordPress post_id
            其他参数同 create_post（传 None 表示不更新该字段）

        Returns:
            WordPress post_id

        Raises:
            httpx.HTTPStatusError: API 调用失败（如 404 表示文章不存在）
        """
        url = f"{self.api_base}/posts/{post_id}"
        payload: dict[str, Any] = {}

        if title is not None:
            payload["title"] = title
        if content is not None:
            payload["content"] = content
        if status is not None:
            payload["status"] = status
        if excerpt is not None:
            payload["excerpt"] = excerpt
        if categories is not None:
            payload["categories"] = categories
        if tags is not None:
            payload["tags"] = tags

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                json=payload,
                auth=(self.username, self.app_password),
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"WordPress post updated: {data['id']} - {data['link']}")
            return data["id"]

    async def delete_post(self, post_id: int, force: bool = False) -> bool:
        """删除文章。

        Args:
            post_id: WordPress post_id
            force: True = 永久删除；False = 移到回收站

        Returns:
            True 表示删除成功

        Raises:
            httpx.HTTPStatusError: API 调用失败
        """
        url = f"{self.api_base}/posts/{post_id}"
        params = {"force": "true" if force else "false"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                url,
                params=params,
                auth=(self.username, self.app_password),
            )
            response.raise_for_status()
            logger.info(f"WordPress post deleted: {post_id} (force={force})")
            return True
