"""发布日志模型（阶段 5）—— 记录每次文章发布操作的结果。

用于：
    - 审计：谁在什么时候发布了哪篇文章到哪个目标
    - 调试：发布失败时查看错误信息
    - 展示：前端显示发布历史
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base import Base


class PublishStatus(str, PyEnum):
    """发布状态枚举。"""

    PENDING = "pending"  # 发布中
    SUCCESS = "success"  # 发布成功
    FAILED = "failed"  # 发布失败


class PublishLog(Base):
    """发布日志表 —— 每次发布操作一条记录。

    字段说明：
        - article_id: 关联文章
        - target_id: 关联发布目标
        - status: pending / success / failed
        - remote_id: 远程文章 ID（如 WordPress 的 post_id）
        - error_message: 失败时的错误信息
        - published_at: 发布时间
        - created_by: 操作人（User ID）
    """

    __tablename__ = "publish_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    article_id = Column(UUID(as_uuid=True), ForeignKey("articles.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id = Column(UUID(as_uuid=True), ForeignKey("publish_targets.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(Enum(PublishStatus), nullable=False, default=PublishStatus.PENDING, comment="pending / success / failed")
    remote_id = Column(String(200), nullable=True, comment="远程文章 ID（如 WP post_id）")
    error_message = Column(Text, nullable=True, comment="失败原因")
    published_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # 关系
    article = relationship("Article", back_populates="publish_logs")
    target = relationship("PublishTarget", back_populates="publish_logs")
    creator = relationship("User")
