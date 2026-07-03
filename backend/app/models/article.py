"""Article — 文章主表（阶段 4 核心）。

业务背景：
    用户在 FNAI 平台"写文章"——基于知识库(KB) + AI 生成 SEO 友好内容。
    一篇文章有：标题 / 正文(markdown) / 状态 / 来自哪个 KB / 用什么模板等。
    支持手工写、AI 生成、生成后再改。

    生命周期：
        DRAFT（草稿/生成中）→ COMPLETED（生成完）→ PUBLISHED（已发布到外部）
                                       ↘ FAILED（生成失败）

数据模型（给 Java 同事的提示 ≈ @Entity + @Table）：

    ┌─────────────────────────────────────────────┐
    │                articles 表                   │
    ├─────────────────────────────────────────────┤
    │ id (UUID PK)                                 │
    │ tenant_id (FK → tenants)                     │  ← 多租户隔离
    │ knowledge_base_id (FK → knowledge_bases)     │  ← 基于哪个 KB 生成（nullable）
    │ template_code (varchar 50)                   │  ← 用了哪个模板（blog/seo/...）
    │ title (varchar 300)                          │  ← 文章标题
    │ topic (varchar 500)                          │  ← 用户输入的"主题"（生成时的 prompt 核心）
    │ content (text)                               │  ← 正文 Markdown
    │ outline (jsonb, nullable)                    │  ← 大纲（生成 pipeline 第一阶段产物）
    │ seo_meta (jsonb, nullable)                   │  ← SEO 元信息（title/desc/keywords）
    │ status (PG ENUM)                             │
    │ word_count (int)                             │  ← 字数（前端排序/过滤用）
    │ error_message (text, nullable)               │  ← 生成失败原因
    │ created_by (FK → users)                      │
    │ created_at / updated_at (mixin)              │
    └─────────────────────────────────────────────┘

设计要点：
    - content 是 Markdown 文本，前端用富文本编辑器渲染
    - outline / seo_meta 用 JSONB（Postgres 原生 JSON，能索引能查询）
    - tenant_id 冗余存：列表查询不用 join
    - knowledge_base_id 可空：允许"不基于知识库"的纯模板生成
"""

import enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Enum as SAEnum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.article_version import ArticleVersion
    from app.models.generation_task import GenerationTask
    from app.models.knowledge_base import KnowledgeBase
    from app.models.publish_log import PublishLog
    from app.models.tenant import Tenant
    from app.models.user import User


# ============================================================
# 业务枚举：文章状态
# ============================================================


class ArticleStatus(str, enum.Enum):
    """文章生命周期。

    流转：
        DRAFT      → COMPLETED → PUBLISHED
        DRAFT/COMPLETED → FAILED（生成失败）
    """

    DRAFT = "draft"            # 草稿 / 正在生成
    COMPLETED = "completed"    # 生成完成，可编辑
    PUBLISHED = "published"    # 已发布到外部平台
    FAILED = "failed"          # 生成失败


# ============================================================
# SQLAlchemy 模型
# ============================================================


class Article(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """文章主表。"""

    __tablename__ = "articles"

    # ---------- 业务字段 ----------

    # 租户 ID（多租户隔离）
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 基于哪个知识库生成（nullable：允许"不基于 KB"的生成）
    # SET NULL：KB 删了，文章保留但失去关联
    knowledge_base_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 用了哪个模板（blog/product/news/seo/social，跟 prompt_template.code 对得上）
    template_code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="blog",
    )

    # 文章标题
    title: Mapped[str] = mapped_column(
        String(300),
        nullable=False,
    )

    # 用户输入的主题（生成时的核心 prompt，例："如何选择适合中小企业的 CRM 系统"）
    topic: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    # 正文（Markdown）
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )

    # 大纲（pipeline 第一阶段产物，JSONB 存结构化数据）
    # 例：[{"heading": "引言", "key_points": [...]}, ...]
    outline: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # SEO 元信息（pipeline 第三阶段产物）
    # 例：{"meta_title": "...", "meta_description": "...", "keywords": [...]}
    seo_meta: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # 状态
    status: Mapped[ArticleStatus] = mapped_column(
        SAEnum(ArticleStatus, name="article_status"),
        default=ArticleStatus.DRAFT,
        nullable=False,
        index=True,
    )

    # 字数（前端排序、用量统计用）
    word_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # 失败原因（status=FAILED 时填）
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 创建者
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ---------- 关系 ----------

    tenant: Mapped["Tenant"] = relationship()
    knowledge_base: Mapped["KnowledgeBase | None"] = relationship()
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by])

    # 一对多：版本历史（手动保存的快照）
    versions: Mapped[list["ArticleVersion"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )

    # 一对多：生成任务（一篇文章可能重生成多次）
    generation_tasks: Mapped[list["GenerationTask"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )

    # 一对多：发布日志
    publish_logs: Mapped[list["PublishLog"]] = relationship(
        back_populates="article",
        cascade="all, delete-orphan",
    )

    # ---------- 索引 ----------

    __table_args__ = (
        # 列表常用：按租户 + 创建时间倒序
        Index("ix_articles_tenant_created", "tenant_id", "created_at"),
        # 列表筛选：按租户 + 状态
        Index("ix_articles_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<Article tenant={self.tenant_id} title={self.title!r} status={self.status.value}>"
