"""微信公众号相关 Schema（阶段 5 — 微信公众号对接）。

概念：Pydantic 数据验证模型，用于 API 请求/响应验证。
模块：schemas/wechat.py
作用：定义微信公众号相关的数据结构
怎么写：
    - 请求 Schema：验证客户端传入的参数
    - 响应 Schema：格式化返回给客户端的数据
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================
# 发布相关 Schema
# ============================================================


class WechatPublishRequest(BaseModel):
    """微信发布请求。

    注意：article_id 已经在路径参数中，不需要在 body 里重复。
    """

    author: Optional[str] = Field(
        default=None,
        max_length=16,
        description="作者名称（可选，默认使用配置中的作者）",
    )

    digest: Optional[str] = Field(
        default=None,
        max_length=120,
        description="文章摘要（可选，默认自动生成）",
    )

    thumb_media_id: Optional[str] = Field(
        default=None,
        description="封面图素材 ID（可选）",
    )

    need_open_comment: bool = Field(
        default=True,
        description="是否打开评论",
    )

    only_fans_can_comment: bool = Field(
        default=False,
        description="是否仅粉丝可评论",
    )


class WechatPublishResponse(BaseModel):
    """微信发布响应。"""

    success: bool = Field(..., description="是否成功")

    message: str = Field(..., description="提示信息")

    publish_id: Optional[str] = Field(
        default=None,
        description="发布任务 ID（用于查询状态）",
    )

    draft_media_id: Optional[str] = Field(
        default=None,
        description="草稿素材 ID",
    )

    fallback: bool = Field(
        default=False,
        description="是否降级处理",
    )

    fallback_strategy: Optional[str] = Field(
        default=None,
        description="降级策略",
    )

    copy_content: Optional[str] = Field(
        default=None,
        description="手动复制内容（降级时有值）",
    )


# ============================================================
# 状态查询相关 Schema
# ============================================================


class WechatPublishStatusRequest(BaseModel):
    """微信发布状态查询请求。"""

    publish_id: str = Field(..., description="发布任务 ID")


class WechatPublishStatusResponse(BaseModel):
    """微信发布状态查询响应。"""

    publish_id: str = Field(..., description="发布任务 ID")

    publish_status: int = Field(
        ...,
        description="发布状态: 0=成功, 1=发布中, 2+=失败原因",
    )

    article_id: Optional[str] = Field(
        default=None,
        description="文章 ID（发布成功后有值）",
    )

    article_url: Optional[str] = Field(
        default=None,
        description="文章链接（发布成功后有值）",
    )

    fail_reason: Optional[str] = Field(
        default=None,
        description="失败原因（发布失败时有值）",
    )


# ============================================================
# 配置相关 Schema
# ============================================================


class WechatConfigCreate(BaseModel):
    """创建微信公众号配置。"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="配置名称（如：公司公众号）",
    )

    app_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="微信公众号 AppID",
    )

    app_secret: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="微信公众号 AppSecret",
    )

    author: Optional[str] = Field(
        default=None,
        max_length=16,
        description="默认作者名称",
    )

    thumb_media_id: Optional[str] = Field(
        default=None,
        description="默认封面图素材 ID",
    )


class WechatConfigUpdate(BaseModel):
    """更新微信公众号配置。"""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="配置名称",
    )

    app_secret: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="微信公众号 AppSecret",
    )

    author: Optional[str] = Field(
        default=None,
        max_length=16,
        description="默认作者名称",
    )

    thumb_media_id: Optional[str] = Field(
        default=None,
        description="默认封面图素材 ID",
    )


class WechatConfigResponse(BaseModel):
    """微信公众号配置响应。"""

    id: UUID = Field(..., description="配置 ID")

    name: str = Field(..., description="配置名称")

    app_id: str = Field(..., description="微信公众号 AppID")

    author: Optional[str] = Field(
        default=None,
        description="默认作者名称",
    )

    is_active: bool = Field(..., description="是否启用")

    created_at: str = Field(..., description="创建时间")

    updated_at: str = Field(..., description="更新时间")

    class Config:
        from_attributes = True


# ============================================================
# 错误响应 Schema
# ============================================================


class WechatErrorResponse(BaseModel):
    """微信公众号错误响应。"""

    code: str = Field(..., description="错误代码")

    message: str = Field(..., description="错误信息")

    wx_errcode: Optional[int] = Field(
        default=None,
        description="微信错误码",
    )

    retryable: bool = Field(
        default=False,
        description="是否可重试",
    )

    fallback_strategy: Optional[str] = Field(
        default=None,
        description="建议的降级策略",
    )
