"""KnowledgeBase — 知识库元数据表。

业务背景：
    一个租户可以有多个知识库（KB），每个 KB 是一组"主题相关"的文档。
    典型场景：
        - KB 1：「公司产品手册」（放产品 PDF/PPT）
        - KB 2：「行业研究报告」（放白皮书）
        - KB 3：「技术博客合集」（放内部技术文档）

    用途是给文章生成做 RAG（Retrieval-Augmented Generation），
    用户写文章时，AI 会从指定 KB 里检索相关内容当素材。

数据模型（给 Java 同事的提示 ≈ @Entity + @Table）：

    ┌────────────────────────────────────────┐
    │       knowledge_bases 表                │
    ├────────────────────────────────────────┤
    │ id (UUID PK)                            │
    │ tenant_id (FK → tenants)                │  ← 多租户隔离
    │ name (varchar 120)                      │  ← 用户起的名字
    │ slug (varchar 80, unique per tenant)    │  ← URL 友好标识
    │ description (text, nullable)            │
    │ created_by (FK → users)                 │  ← 谁建的
    │ created_at / updated_at (mixin)         │
    └────────────────────────────────────────┘

复合唯一约束：
    - (tenant_id, slug) unique → 同一租户下 KB 标识不能重
      但不同租户可以有同名 KB（多租户数据隔离）
"""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.tenant import Tenant
    from app.models.user import User


class KnowledgeBase(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """知识库元数据。

    ⚠️ 重要：这张表只存"知识库的描述信息"，文档内容在 documents/chunks 表里。
    """

    __tablename__ = "knowledge_bases"

    # ---------- 业务字段 ----------

    # 属于哪个租户（多租户隔离的核心字段）
    # CASCADE：租户被删时，知识库一起删
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,  # 查"这个租户的所有 KB" 必备
    )

    # KB 名字（用户起的）
    name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
    )

    # slug：URL 友好的标识，比如 "product-manual"
    # 同一租户下不能重复，但跨租户可以重名
    slug: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
    )

    # 描述（可选）
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 创建者
    # SET NULL：创建者账号被删了，KB 还在（不级联）
    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ---------- 关系（Relationships）----------

    # 多对一：属于某个租户
    tenant: Mapped["Tenant"] = relationship()

    # 多对一：创建者
    creator: Mapped["User | None"] = relationship(
        foreign_keys=[created_by],
    )

    # 一对多：这个 KB 下的所有文档
    # cascade="all, delete-orphan"：KB 删了，文档也一起删
    documents: Mapped[list["Document"]] = relationship(
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )

    # ---------- 复合约束 ----------

    __table_args__ = (
        # 同一租户下 slug 不能重
        UniqueConstraint(
            "tenant_id",
            "slug",
            name="uq_knowledge_bases_tenant_slug",
        ),
        # 租户 + 创建时间 复合索引（用于"最新创建"排序）
        Index(
            "ix_knowledge_bases_tenant_created",
            "tenant_id",
            "created_at",
        ),
    )

    def __repr__(self) -> str:
        return f"<KnowledgeBase tenant={self.tenant_id} name={self.name!r} slug={self.slug!r}>"
