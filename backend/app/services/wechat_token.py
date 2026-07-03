"""微信 access_token 管理服务（阶段 5 — 微信公众号对接）。

概念：微信 access_token 是调用微信 API 的凭证，有效期 2 小时。
模块：services/wechat_token.py
作用：获取/缓存/刷新 access_token
怎么写：
    - 使用数据库缓存 token，避免频繁请求微信服务器
    - 使用 asyncio.Lock 防止并发刷新
    - 提前 5 分钟刷新，避免边界问题
    - 每次刷新都更新缓存
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.wechat_token_cache import WechatTokenCache

logger = logging.getLogger(__name__)


class WechatTokenError(Exception):
    """Token 获取失败。"""

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class WechatTokenManager:
    """微信 access_token 管理器。

    使用方法：
        manager = WechatTokenManager(db)
        token = await manager.get_token(app_id, app_secret)

    设计要点：
        - 每个 app_id 独立管理 token
        - 使用数据库缓存，支持多实例部署
        - 使用 asyncio.Lock 防止同一 app_id 并发刷新
        - 提前 5 分钟刷新，避免边界问题
    """

    # 微信 token 接口
    TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"

    # 提前 5 分钟刷新
    REFRESH_BUFFER = timedelta(minutes=5)

    # 全局锁字典，每个 app_id 独立的锁
    _locks: dict[str, asyncio.Lock] = {}

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_token(self, app_id: str, app_secret: str) -> str:
        """获取有效的 access_token，优先从缓存读取。

        Args:
            app_id: 微信公众号 AppID
            app_secret: 微信公众号 AppSecret

        Returns:
            有效的 access_token 字符串

        Raises:
            WechatTokenError: 获取失败
        """
        # 获取或创建该 app_id 的锁
        if app_id not in self._locks:
            self._locks[app_id] = asyncio.Lock()

        async with self._locks[app_id]:
            # 1. 尝试从缓存读取
            cached = await self._get_cached_token(app_id)
            if cached and not cached.is_expired(buffer_seconds=300):
                logger.debug(f"Using cached token for app_id={app_id}")
                return cached.access_token

            # 2. 缓存过期或不存在，请求新 token
            logger.info(f"Refreshing token for app_id={app_id}")
            token_data = await self._request_token(app_id, app_secret)

            # 3. 更新缓存
            await self._update_cache(app_id, token_data)

            return token_data["access_token"]

    async def invalidate_cache(self, app_id: str) -> None:
        """使缓存的 token 失效（用于强制刷新）。

        Args:
            app_id: 微信公众号 AppID
        """
        stmt = select(WechatTokenCache).where(
            WechatTokenCache.app_id == app_id
        )
        result = await self.db.execute(stmt)
        cached = result.scalar_one_or_none()

        if cached:
            # 设置为过期
            cached.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            await self.db.commit()
            logger.info(f"Invalidated token cache for app_id={app_id}")

    async def _request_token(self, app_id: str, app_secret: str) -> dict:
        """向微信服务器请求 access_token。

        微信接口说明：
            URL: https://api.weixin.qq.com/cgi-bin/token
            参数:
                - grant_type: 固定为 "client_credential"
                - appid: 公众号 AppID
                - secret: 公众号 AppSecret
            返回:
                - access_token: 凭证
                - expires_in: 有效时间（秒），通常为 7200

        Raises:
            WechatTokenError: 请求失败
        """
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                response = await client.get(
                    self.TOKEN_URL,
                    params={
                        "grant_type": "client_credential",
                        "appid": app_id,
                        "secret": app_secret,
                    },
                )
                data = response.json()
            except httpx.TimeoutException:
                raise WechatTokenError(code=-1, message="请求微信服务器超时")
            except httpx.NetworkError as e:
                raise WechatTokenError(code=-1, message=f"网络错误: {e}")

            # 检查错误
            if "errcode" in data and data["errcode"] != 0:
                error_code = data["errcode"]
                error_msg = data.get("errmsg", "未知错误")
                logger.error(
                    f"Failed to get token: errcode={error_code}, errmsg={error_msg}"
                )
                raise WechatTokenError(
                    code=error_code,
                    message=f"获取 token 失败: {error_msg}",
                )

            # 验证返回数据
            if "access_token" not in data or "expires_in" not in data:
                raise WechatTokenError(
                    code=-1,
                    message=f"微信返回数据异常: {data}",
                )

            return data

    async def _get_cached_token(self, app_id: str) -> Optional[WechatTokenCache]:
        """从数据库获取缓存的 token。"""
        stmt = select(WechatTokenCache).where(
            WechatTokenCache.app_id == app_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _update_cache(self, app_id: str, token_data: dict) -> None:
        """更新或插入 token 缓存。"""
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=token_data["expires_in"]
        )

        # 查询是否已存在
        stmt = select(WechatTokenCache).where(
            WechatTokenCache.app_id == app_id
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # 更新
            existing.access_token = token_data["access_token"]
            existing.expires_at = expires_at
            logger.info(f"Updated token cache for app_id={app_id}")
        else:
            # 新增
            cache = WechatTokenCache(
                app_id=app_id,
                access_token=token_data["access_token"],
                expires_at=expires_at,
            )
            self.db.add(cache)
            logger.info(f"Created token cache for app_id={app_id}")

        await self.db.commit()
