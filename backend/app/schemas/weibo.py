"""微博相关 Schema（阶段 5 — 微博对接）。

概念：Pydantic 数据验证模型，用于 API 请求/响应验证。
模块：schemas/weibo.py
作用：定义微博相关的数据结构
"""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============================================================
# 发布相关 Schema
# ============================================================


class WeiboPublishRequest(BaseModel):
    """微博发布请求。"""

    content: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="微博正文内容（可选，默认取文章摘要）",
    )

    suffix: Optional[str] = Field(
        default=None,
        max_length=200,
        description="微博尾部追加内容（如话题标签 #医药健康#）",
    )

    image_url: Optional[str] = Field(
        default=None,
        description="配图 URL（可选）",
    )


class WeiboPublishResponse(BaseModel):
    """微博发布响应。"""

    success: bool = Field(..., description="是否成功")

    message: str = Field(..., description="提示信息")

    publish_id: Optional[str] = Field(
        default=None,
        description="发布任务 ID（用于查询状态）",
    )

    weibo_id: Optional[str] = Field(
        default=None,
        description="微博 ID（发布成功后有值）",
    )

    weibo_url: Optional[str] = Field(
        default=None,
        description="微博链接（发布成功后有值）",
    )


# ============================================================
# 状态查询相关 Schema
# ============================================================


class WeiboPublishStatusResponse(BaseModel):
    """微博发布状态查询响应。"""

    publish_id: str = Field(..., description="发布任务 ID")

    status: str = Field(..., description="发布状态: pending/success/failed")

    weibo_id: Optional[str] = Field(
        default=None,
        description="微博 ID（发布成功后有值）",
    )

    weibo_url: Optional[str] = Field(
        default=None,
        description="微博链接（发布成功后有值）",
    )

    fail_reason: Optional[str] = Field(
        default=None,
        description="失败原因（发布失败时有值）",
    )


# ============================================================
# 配置相关 Schema
# ============================================================


class WeiboConfigCreate(BaseModel):
    """创建微博配置。"""

    name: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="配置名称（如：公司微博号）",
    )

    cookie: str = Field(
        ...,
        min_length=1,
        description="微博登录 Cookie（从浏览器开发者工具获取）",
    )

    default_suffix: Optional[str] = Field(
        default=None,
        max_length=200,
        description="默认微博尾部内容（如话题标签）",
    )


class WeiboConfigUpdate(BaseModel):
    """更新微博配置。"""

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="配置名称",
    )

    cookie: Optional[str] = Field(
        default=None,
        min_length=1,
        description="微博登录 Cookie",
    )

    default_suffix: Optional[str] = Field(
        default=None,
        max_length=200,
        description="默认微博尾部内容",
    )


class WeiboConfigResponse(BaseModel):
    """微博配置响应。"""

    id: UUID = Field(..., description="配置 ID")

    name: str = Field(..., description="配置名称")

    cookie_preview: Optional[str] = Field(
        default=None,
        description="Cookie 预览（脱敏，只显示前20字符）",
    )

    default_suffix: Optional[str] = Field(
        default=None,
        description="默认微博尾部内容",
    )

    is_active: bool = Field(..., description="是否启用")

    created_at: str = Field(..., description="创建时间")

    updated_at: str = Field(..., description="更新时间")

    class Config:
        from_attributes = True


# ============================================================
# 错误响应 Schema
# ============================================================


class WeiboErrorResponse(BaseModel):
    """微博错误响应。"""

    code: str = Field(..., description="错误代码")

    message: str = Field(..., description="错误信息")

    retryable: bool = Field(
        default=False,
        description="是否可重试",
    )
