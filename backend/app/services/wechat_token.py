"""微信 access_token 管理服务（阶段 5 — 微信公众号对接）。

概念：微信 access_token 是调用微信 API 的凭证，有效期 2 小时。
模块：services/wechat_token.py
作用：获取/缓存/刷新 access_token
怎么写：
    - 使用数据库缓存 token，避免频繁请求微信服务器
    - 使用数据库行锁（SELECT FOR UPDATE）实现分布式锁，支持多进程部署
    - 提前 5 分钟刷新，避免边界问题
    - 每次刷新都更新缓存
"""

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
        - 使用 SELECT FOR UPDATE 行锁实现分布式锁，防止多进程并发刷新
        - 提前 5 分钟刷新，避免边界问题
        - Double-check 模式：先无锁快速查询，缓存失效时加锁后再次检查
    """

    # 微信 token 接口
    TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"

    # 提前 5 分钟刷新
    REFRESH_BUFFER = timedelta(minutes=5)

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_token(self, app_id: str, app_secret: str) -> str:
        """获取有效的 access_token，优先从缓存读取。

        使用数据库行锁实现分布式锁，支持多进程/多实例部署。

        Args:
            app_id: 微信公众号 AppID
            app_secret: 微信公众号 AppSecret

        Returns:
            有效的 access_token 字符串

        Raises:
            WechatTokenError: 获取失败
        """
        # 1. 先无锁查询，快速路径
        cached = await self._get_cached_token(app_id)
        if cached and not cached.is_expired(buffer_seconds=300):
            logger.debug(f"Using cached token for app_id={app_id}")
            return cached.access_token

        # 2. 缓存过期或不存在，获取行锁后再次检查（double-check）
        cached_locked = await self._get_cached_token_for_update(app_id)

        # 再次检查是否已被其他进程刷新
        if cached_locked and not cached_locked.is_expired(buffer_seconds=300):
            logger.debug(f"Token refreshed by another process for app_id={app_id}")
            await self.db.commit()  # 释放锁
            return cached_locked.access_token

        # 3. 确认需要刷新，请求新 token
        logger.info(f"Refreshing token for app_id={app_id}")
        token_data = await self._request_token(app_id, app_secret)

        # 4. 更新缓存（持有行锁，不会冲突）
        await self._update_cache_locked(app_id, cached_locked, token_data)

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
        """从数据库获取缓存的 token（无锁，快速查询）。"""
        stmt = select(WechatTokenCache).where(
            WechatTokenCache.app_id == app_id
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_cached_token_for_update(self, app_id: str) -> Optional[WechatTokenCache]:
        """获取缓存 token 并加行锁（SELECT ... FOR UPDATE）。

        这是分布式锁的关键：持有行锁期间，其他进程/实例会阻塞在此。
        如果记录不存在，创建一个占位记录并加锁。
        """
        stmt = select(WechatTokenCache).where(
            WechatTokenCache.app_id == app_id
        ).with_for_update()

        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            return existing

        # 记录不存在，创建占位记录（过期时间设为过去，确保需要刷新）
        placeholder = WechatTokenCache(
            app_id=app_id,
            access_token="",  # 占位，稍后更新
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        self.db.add(placeholder)
        await self.db.flush()  # flush 使其获得 ID，但不 commit

        # 重新查询并加锁
        stmt = select(WechatTokenCache).where(
            WechatTokenCache.app_id == app_id
        ).with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _update_cache_locked(
        self,
        app_id: str,
        cached: Optional[WechatTokenCache],
        token_data: dict
    ) -> None:
        """更新 token 缓存（调用前必须已持有行锁）。"""
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=token_data["expires_in"]
        )

        if cached:
            # 更新现有记录
            cached.access_token = token_data["access_token"]
            cached.expires_at = expires_at
            logger.info(f"Updated token cache for app_id={app_id}")
        else:
            # 理论上不会走到这里（_get_cached_token_for_update 会创建占位）
            cache = WechatTokenCache(
                app_id=app_id,
                access_token=token_data["access_token"],
                expires_at=expires_at,
            )
            self.db.add(cache)
            logger.info(f"Created token cache for app_id={app_id}")

        await self.db.commit()  # commit 时释放行锁
