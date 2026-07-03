"""Article + ArticleVersion + PromptTemplate 的请求/响应数据契约（阶段 4 Step 2）。

设计原则跟 schemas/knowledge.py 一致：
- 响应不带 tenant_id / created_by 等内部字段（除非业务需要）
- 创建/更新只接受业务字段
- ConfigDict(from_attributes=True) 让 Pydantic 能直接 ORM → DTO
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Article
# ============================================================


class ArticleCreate(BaseModel):
    """POST /articles 的请求体（手工创建空白文章 / 等待生成）。"""

    title: str = Field(min_length=1, max_length=300, description="文章标题")
    topic: str = Field(min_length=1, max_length=500, description="主题（生成 prompt 的核心）")
    template_code: str = Field(
        default="blog",
        max_length=50,
        description="模板代码（blog/product/news/seo/social）",
    )
    knowledge_base_id: UUID | None = Field(default=None, description="基于哪个 KB（可空）")
    content: str = Field(default="", description="初始正文，留空让 AI 生成")


class ArticleUpdate(BaseModel):
    """PATCH /articles/{id} 的请求体（编辑器保存用）。"""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: str | None = Field(default=None, description="正文 Markdown")
    seo_meta: dict[str, Any] | None = Field(default=None, description="SEO 元信息")


class ArticleRead(BaseModel):
    """GET /articles/{id} 详情的响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    topic: str
    template_code: str
    knowledge_base_id: UUID | None
    content: str
    outline: dict[str, Any] | None
    seo_meta: dict[str, Any] | None
    status: str
    word_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class ArticleSummary(BaseModel):
    """列表里的精简版（不带 content 大字段，省流量）。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    topic: str
    template_code: str
    knowledge_base_id: UUID | None
    status: str
    word_count: int
    created_at: datetime
    updated_at: datetime


class ArticleListResponse(BaseModel):
    items: list[ArticleSummary]
    total: int


# ============================================================
# ArticleVersion
# ============================================================


class VersionCreate(BaseModel):
    """POST /articles/{id}/versions 的请求体（打快照）。"""

    note: str | None = Field(default=None, max_length=200, description="修订说明")


class VersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    article_id: UUID
    version_no: int
    title: str
    content: str
    note: str | None
    created_at: datetime


class VersionListResponse(BaseModel):
    items: list[VersionRead]
    total: int


# ============================================================
# PromptTemplate
# ============================================================


class TemplateSummary(BaseModel):
    """GET /templates 列表元素（只暴露挑选用的字段，不暴露 prompt 全文）。"""

    model_config = ConfigDict(from_attributes=True)

    code: str
    name: str
    description: str
    default_word_count: int
    template_type: str


class TemplateListResponse(BaseModel):
    items: list[TemplateSummary]
    total: int


# ============================================================
# Generation（生成）
# ============================================================


class GenerationRequest(BaseModel):
    """POST /articles/{id}/generate 的请求体。"""

    target_word_count: int | None = Field(
        default=None, ge=200, le=10000,
        description="目标字数；不传用模板默认值",
    )
