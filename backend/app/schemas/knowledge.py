"""知识库（KnowledgeBase）+ 文档（Document）的请求/响应数据契约。

给 Java 同事的提示：
- BaseModel ≈ Java 的 record
- ConfigDict(from_attributes=True) ≈ Jackson 的 @JsonAutoDetect
- Field(...) ≈ @NotNull + @Size 等

⚠️ 设计原则：
- 响应里**不暴露 storage_key**（那是后端内部细节）
- 响应里**不带 tenant_id**（租户上下文在 JWT 里，前端不需要重复传）
- 写操作只接受业务字段，tenant_id 永远从 token 取
"""

import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# slug 规则：小写字母/数字/连字符，不能以连字符开头/结尾
SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$"


# ============================================================
# KnowledgeBase
# ============================================================


class KnowledgeBaseCreate(BaseModel):
    """POST /knowledge 的请求体。

    ⚠️ 故意不带 tenant_id：从 JWT 的 active_tenant_id 取。
    """

    # KB 名字（用户起的）
    name: str = Field(
        min_length=1,
        max_length=120,
        description="知识库名字",
        examples=["公司产品手册"],
    )

    # slug：URL 友好标识
    # 校验：必须符合 SLUG_PATTERN（小写+数字+连字符）
    slug: str = Field(
        min_length=1,
        max_length=80,
        description="URL 友好标识（小写字母/数字/连字符）",
        examples=["product-manual"],
    )

    # 描述（可选）
    description: str | None = Field(
        default=None,
        max_length=2000,
        description="知识库描述（可选）",
    )

    @field_validator("slug")
    @classmethod
    def _validate_slug_format(cls, v: str) -> str:
        """slug 必须小写字母/数字/连字符。"""
        if not re.match(SLUG_PATTERN, v):
            raise ValueError(
                "slug 必须是小写字母/数字/连字符，且不能以连字符开头或结尾"
            )
        return v


class KnowledgeBaseRead(BaseModel):
    """GET /knowledge 列表 / GET /knowledge/{id} 详情的响应。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    # 统计：包含多少个文档（前端首页展示用）
    document_count: int = 0


class KnowledgeBaseListResponse(BaseModel):
    """GET /knowledge 列表的响应。"""

    items: list[KnowledgeBaseRead]
    total: int


# ============================================================
# Document
# ============================================================


class DocumentRead(BaseModel):
    """GET /knowledge/{kb_id}/documents 列表 / GET /knowledge/.../documents/{id} 详情的响应。

    ⚠️ 故意不带 storage_key（后端内部细节）
    ⚠️ 故意不带 tenant_id / knowledge_base_id（路径里已经有了）
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    status: str  # DocumentStatus 的值
    error_message: str | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime
    # 处理完时间（status=ready 时才填）
    # ⚠️ 用 alias 兼容 ORM 属性名（如果加）


class DocumentListResponse(BaseModel):
    """GET /knowledge/{kb_id}/documents 的响应。"""

    items: list[DocumentRead]
    total: int
    # 按状态的统计（前端展示"PENDING: 3, READY: 10, FAILED: 1"用）
    pending_count: int = 0
    ready_count: int = 0
    failed_count: int = 0


# ============================================================
# Search（语义检索，Step 4）
# ============================================================


class SearchRequest(BaseModel):
    """POST /knowledge/{kb_id}/search 的请求体。

    把 query 向量化后，在该 KB 的 chunk 里找语义最相近的若干条。
    """

    # 查询文本（用户问的问题 / 要检索的关键词）
    query: str = Field(
        min_length=1,
        max_length=1000,
        description="检索查询文本",
        examples=["FNAI 有哪些核心功能"],
    )

    # 返回前 K 条最相似的（默认 5，给 RAG 喂上下文够用）
    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
        description="返回最相似的前 K 条",
    )

    # 相似度阈值（可选）：只返回 score >= min_score 的结果，过滤勉强沾边的
    # 余弦相似度范围 [-1, 1]，实际文本通常落在 [0, 1]
    min_score: float | None = Field(
        default=None,
        ge=-1.0,
        le=1.0,
        description="相似度阈值（可选）；不传则不过滤",
        examples=[0.5],
    )


class SearchResultItem(BaseModel):
    """单条检索命中（一个 chunk + 它的来源文档信息 + 相似度分数）。"""

    chunk_id: UUID
    # 来源文档（前端展示"引用自 xx.pdf"用）
    document_id: UUID
    filename: str
    # chunk 在文档里的序号 + 字符位置（前端可跳回原文定位高亮）
    chunk_index: int
    char_start: int
    char_end: int
    # chunk 正文
    content: str
    # 余弦相似度，1 = 完全一致，越大越相似（= 1 - cosine_distance）
    score: float


class SearchResponse(BaseModel):
    """POST /knowledge/{kb_id}/search 的响应。"""

    query: str
    items: list[SearchResultItem]
    total: int


# ============================================================
# 工具函数
# ============================================================


def validate_slug(slug: str) -> None:
    """显式校验 slug 格式（Pydantic pattern 已经做了，这里是双保险）。

    Raises:
        ValueError: slug 不合规
    """
    if not re.match(SLUG_PATTERN, slug):
        raise ValueError(
            "slug 必须是小写字母/数字/连字符，且不能以连字符开头或结尾"
        )
