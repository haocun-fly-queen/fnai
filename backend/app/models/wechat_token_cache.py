"""微信 access_token 缓存模型（阶段 5 — 微信公众号对接）。

概念：缓存微信 access_token，避免频繁请求微信服务器。
模块：models/wechat_token_cache.py
作用：存储 access_token 和过期时间
怎么写：
    - access_token 有效期 2 小时，需要缓存
    - 每个公众号独立缓存（通过 app_id 区分）
    - 过期后自动刷新
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WechatTokenCache(Base):
    """微信 access_token 缓存表。

    存储每个公众号的 access_token，避免频繁请求微信服务器。

    字段说明：
        - app_id: 公众号 AppID（唯一索引）
        - access_token: 微信返回的 access_token
        - expires_at: 过期时间（微信返回 expires_in 秒数，转换为绝对时间）
    """

    __tablename__ = "wechat_token_cache"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        default=lambda: str(uuid4()),
        comment="主键 ID",
    )

    app_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        comment="微信公众号 AppID",
    )

    access_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="微信 access_token",
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="过期时间（UTC）",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )

    def __repr__(self) -> str:
        return f"<WechatTokenCache app_id={self.app_id} expires_at={self.expires_at}>"

    def is_expired(self, buffer_seconds: int = 300) -> bool:
        """检查 token 是否已过期。

        Args:
            buffer_seconds: 提前量（秒），默认 5 分钟

        Returns:
            True 表示已过期或即将过期
        """
        from datetime import timedelta, timezone
        now = datetime.now(timezone.utc)
        buffer = timedelta(seconds=buffer_seconds)
        return now >= (self.expires_at - buffer)
