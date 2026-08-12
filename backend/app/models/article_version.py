"""ArticleVersion — 文章版本快照表。

业务背景：
    用户改文章可能改坏，需要"回到上一版"的能力。
    每次手动保存（或 AI 重新生成）时打一个快照存到这张表。
    类似 git commit 但极简——只存 title + content + 简短说明。

    V1 仅做手工触发的快照（不做"每次输入都自动存"）。

数据模型：

    ┌────────────────────────────────────────┐
    │         article_versions 表             │
    ├────────────────────────────────────────┤
    │ id (UUID PK)                            │
    │ article_id (FK → articles)              │
    │ tenant_id (FK → tenants)                │  ← 冗余存便于隔离
    │ version_no (int)                        │  ← 第几个版本，从 1 起
    │ title (varchar 300)                     │
    │ content (text)                          │
    │ note (varchar 200, nullable)            │  ← 用户写的修订说明
    │ created_by (FK → users)                 │
    │ created_at (mixin)                      │
    └────────────────────────────────────────┘
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.article import Article
    from app.models.tenant import Tenant
    from app.models.user import User


class ArticleVersion(Base, UUIDPrimaryKeyMixin):
    """文章历史版本快照。

    注：这里没用 TimestampMixin（不需要 updated_at，快照是不可变的）。
    """

    __tablename__ = "article_versions"

    # ---------- 关联 ----------

    article_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 冗余 tenant_id，按租户过滤不用 join articles
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ---------- 快照内容 ----------

    # 同一文章内 version_no 从 1 递增
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 用户的修订说明（可选，"修复了第二段的错别字"）
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 显式 created_at（不复用 TimestampMixin 因为不要 updated_at）
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ---------- 关系 ----------

    article: Mapped["Article"] = relationship(back_populates="versions")
    tenant: Mapped["Tenant"] = relationship()
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by])

    # ---------- 约束 ----------

    __table_args__ = (
        # 同一文章内版本号不能重
        UniqueConstraint("article_id", "version_no", name="uq_article_versions_article_no"),
        Index("ix_article_versions_article_created", "article_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ArticleVersion article={self.article_id} v{self.version_no}>"
