"""发布相关的 Pydantic schema（阶段 5）"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class PublishTargetType(str, Enum):
    """发布目标类型枚举。"""

    WORDPRESS = "wordpress"
    WEBHOOK = "webhook"
    WEIBO = "WEIBO"


class PublishStatus(str, Enum):
    """发布状态枚举。"""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


# === 发布目标 CRUD ===


class PublishTargetCreate(BaseModel):
    """创建发布目标的请求体。"""

    name: str = Field(..., max_length=100, description="目标名称（如'公司官网'）")
    type: PublishTargetType = Field(..., description="wordpress / webhook")
    config: dict = Field(..., description="配置 JSON（site_url / webhook_url 等）")
    is_active: bool = Field(default=True, description="是否启用")


class PublishTargetUpdate(BaseModel):
    """更新发布目标的请求体。"""

    name: str | None = Field(None, max_length=100)
    config: dict | None = None
    is_active: bool | None = None


class PublishTargetResponse(BaseModel):
    """发布目标响应体。"""

    id: UUID
    tenant_id: UUID
    name: str
    type: PublishTargetType
    config: dict
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# === 发布操作 ===


class PublishRequest(BaseModel):
    """发布文章的请求体。"""

    target_id: UUID = Field(..., description="发布目标 ID")
    status: str = Field(default="draft", description="WordPress status: draft / publish")


class PublishResponse(BaseModel):
    """发布结果响应体。"""

    success: bool
    message: str
    remote_id: str | None = Field(None, description="远程文章 ID（如 WP post_id）")
    log_id: UUID | None = Field(None, description="发布日志 ID")
    action: str | None = Field(None, description="操作类型：created（新建）/ updated（更新）")


# === 批量发布 ===


class BatchPublishRequest(BaseModel):
    """POST /articles/batch-publish 的请求体。

    一次把多篇文章发布到多个目标。后端为每个 (文章, 目标) 组合
    异步投递一个 Celery 任务，前端轮询 publish-logs 查看各自状态。
    """

    article_ids: list[UUID] = Field(
        min_length=1, max_length=50, description="待发布的文章 ID 列表（1-50 篇）"
    )
    target_ids: list[UUID] = Field(
        min_length=1, max_length=20, description="发布目标 ID 列表（1-20 个）"
    )
    status: str = Field(default="draft", description="WordPress status: draft / publish")


class BatchPublishResponse(BaseModel):
    """POST /articles/batch-publish 的响应。"""

    task_count: int = Field(description="已投递的发布任务数（文章数 × 目标数）")
    article_ids: list[UUID] = Field(description="参与批量发布的文章 ID 列表")
    message: str = Field(default="批量发布任务已提交，请轮询各文章发布历史")


# === 发布日志查询 ===


class PublishLogResponse(BaseModel):
    """发布日志响应体（完整版，供需要详细信息的场景）。"""

    id: UUID
    article_id: UUID
    target_id: UUID
    status: PublishStatus
    remote_id: str | None
    error_message: str | None
    published_at: datetime
    created_by: UUID | None

    # 关联信息（可选，前端展示用）
    target_name: str | None = None
    article_title: str | None = None

    class Config:
        from_attributes = True


class PublishLogSimpleResponse(BaseModel):
    """发布日志响应体（简化版）—— 只返回是否已发布和发布时间。"""

    is_published: bool = Field(..., description="是否已发布成功")
    published_at: datetime = Field(..., description="发布时间（包括失败的尝试）")
    target_name: str = Field(..., description="发布目标名称（如'微信公众号'）")
    target_id: UUID | None = Field(None, description="发布目标 ID")

    class Config:
        from_attributes = True
