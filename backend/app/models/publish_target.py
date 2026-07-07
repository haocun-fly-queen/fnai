"""发布目标配置模型（阶段 5）—— 存储 WordPress / Webhook 等外部发布端点。

每个租户可以配置多个发布目标（如"公司官网 WP"、"个人博客"等），
文章可以一键发布到这些目标。
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class PublishTargetType(str, PyEnum):
    """发布目标类型枚举。"""

    WORDPRESS = "WORDPRESS"  # WordPress REST API（PG 存大写）
    WEBHOOK = "WEBHOOK"  # 自定义 Webhook
    WECHAT_MP = "WECHAT_MP"  # 微信公众号
    WEIBO = "WEIBO"  # 微博


class PublishTarget(Base):
    """发布目标配置表 —— 存储外部发布端点的连接信息。

    字段说明：
        - tenant_id: 租户 ID（隔离）
        - name: 目标名称（如"公司官网"、"技术博客"）
        - type: wordpress / webhook
        - config: JSONB 存配置
            - WordPress: {"site_url": "...", "username": "...", "app_password": "..."}
            - Webhook: {"webhook_url": "...", "headers": {...}}
        - is_active: 是否启用（可暂时禁用某个目标）
    """

    __tablename__ = "publish_targets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False, comment="目标名称（如'公司官网 WP'）")
    type = Column(Enum(PublishTargetType), nullable=False, comment="wordpress / webhook")
    config = Column(JSONB, nullable=False, comment="配置 JSON（site_url / webhook_url 等）")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否启用")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关系
    tenant = relationship("Tenant", back_populates="publish_targets")
    publish_logs = relationship("PublishLog", back_populates="target", cascade="all, delete-orphan")
