"""PromptTemplate — Prompt 模板表。

业务背景：
    文章生成的"配方"。不同类型文章（博客/产品介绍/新闻稿/SEO/社交）有不同的
    生成策略——大纲结构、语气、长度、SEO 重点都不一样。
    模板把这些差异沉淀成"配方"：一个 prompt 模板 + 一些参数（目标字数等）。

    V1 预置 5 个系统模板（template_type='system'，所有租户共享）：
        - blog       博客文章
        - product    产品介绍
        - news       新闻稿
        - seo        SEO 长文
        - social     社交媒体短文

    V1.5 计划支持租户自定义模板（template_type='custom'，tenant_id 非空）。

数据模型：

    ┌────────────────────────────────────────────┐
    │            prompt_templates 表              │
    ├────────────────────────────────────────────┤
    │ id (UUID PK)                                │
    │ tenant_id (FK → tenants, nullable)          │  ← 系统模板 NULL，自定义模板填租户
    │ code (varchar 50, unique-ish)               │  ← 唯一标识（"blog"/"seo"...）
    │ name (varchar 120)                          │  ← 展示名
    │ description (text)                          │
    │ template_type (PG ENUM: system/custom)      │
    │ outline_prompt (text)                       │  ← pipeline 第一阶段的 prompt
    │ section_prompt (text)                       │  ← 第二阶段（写正文）
    │ seo_prompt (text)                           │  ← 第三阶段（生成 SEO 元数据）
    │ quality_prompt (text)                       │  ← 第四阶段（润色/质量检查）
    │ default_word_count (int, default 1500)      │  ← 默认目标字数
    │ is_active (bool, default True)              │
    │ created_at / updated_at (mixin)             │
    └────────────────────────────────────────────┘

设计要点：
    - 四个 prompt 字段对应生成 pipeline 的四个阶段
    - code 在"系统模板内"必须唯一，"自定义模板"按 (tenant_id, code) 唯一
    - tenant_id 为 NULL 表示系统级（V1 都是这种）
"""

import enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class TemplateType(str, enum.Enum):
    """模板归属类型。"""

    SYSTEM = "system"      # 系统预置，所有租户可用
    CUSTOM = "custom"      # 租户自定义（V1.5 才用）


class PromptTemplate(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Prompt 模板：文章生成的"配方"。"""

    __tablename__ = "prompt_templates"

    # ---------- 归属 ----------

    # 租户 ID（系统模板为 NULL，自定义模板填租户 ID）
    tenant_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    template_type: Mapped[TemplateType] = mapped_column(
        SAEnum(TemplateType, name="prompt_template_type"),
        default=TemplateType.SYSTEM,
        nullable=False,
    )

    # ---------- 标识与描述 ----------

    # 模板代码（blog/product/news/seo/social），articles.template_code 引用这个
    code: Mapped[str] = mapped_column(String(50), nullable=False)

    # 展示名（"博客文章"）
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # 描述（前端选择模板时给用户看）
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # ---------- 四阶段 Prompt ----------

    # 第一阶段：生成大纲
    outline_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # 第二阶段：按大纲写各段正文
    section_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # 第三阶段：生成 SEO 元信息（meta_title/meta_description/keywords）
    seo_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # 第四阶段：质量检查 + 润色
    quality_prompt: Mapped[str] = mapped_column(Text, nullable=False)

    # ---------- 配置 ----------

    # 默认目标字数（用户可在生成时覆盖）
    default_word_count: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)

    # 是否启用
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # ---------- 关系 ----------

    tenant: Mapped["Tenant | None"] = relationship()

    # ---------- 约束与索引 ----------

    __table_args__ = (
        # 系统模板 code 全局唯一；自定义模板 (tenant_id, code) 唯一
        # 这里用一个普通的 unique index 在 (tenant_id, code) 上，
        # tenant_id 为 NULL 时 Postgres 默认允许多行，所以系统模板的"全局唯一"
        # 改用一个 partial unique index 实现
        UniqueConstraint(
            "tenant_id", "code",
            name="uq_prompt_templates_tenant_code",
        ),
        Index(
            "ix_prompt_templates_system_code",
            "code",
            unique=True,
            postgresql_where="tenant_id IS NULL",  # 系统模板 code 全局唯一
        ),
    )

    def __repr__(self) -> str:
        return f"<PromptTemplate code={self.code!r} type={self.template_type.value}>"
