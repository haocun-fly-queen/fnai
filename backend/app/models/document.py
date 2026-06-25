"""Document — 上传的知识库文档元数据。

业务背景：
    用户把 PDF/Word/MD/TXT 上传到知识库，原始文件存 MinIO，
    这张表只存"元数据 + 处理状态"。

    状态机：
        PENDING    → 刚上传，Celery 还没处理
        PROCESSING → Celery 正在解析 + embedding
        READY      → 处理完，可以检索了
        FAILED     → 处理失败（解析报错 / embedding API 限流 等）

数据模型（给 Java 同事的提示 ≈ @Entity + @Table）：

    ┌────────────────────────────────────────┐
    │            documents 表                 │
    ├────────────────────────────────────────┤
    │ id (UUID PK)                            │
    │ tenant_id (FK → tenants)                │  ← 多租户隔离（冗余存为了查询方便）
    │ knowledge_base_id (FK → knowledge_bases)│  ← 属于哪个 KB
    │ filename (varchar 255)                  │  ← 原始文件名
    │ content_type (varchar 100)              │  ← MIME
    │ size_bytes (bigint)                     │  ← 文件大小
    │ storage_key (varchar 512)               │  ← MinIO 里的对象 key
    │ status (PG ENUM)                        │
    │ error_message (text, nullable)          │  ← 失败原因
    │ chunk_count (int, default 0)            │  ← 切了多少个 chunk（处理完才填）
    │ uploaded_by (FK → users)                │
    │ created_at / updated_at (mixin)         │
    └────────────────────────────────────────┘

⚠️ 设计要点：
    - tenant_id 冗余存：query 时不用 join tenants 就能过滤
    - status 用 PG ENUM：4 个值固定，节省空间
    - storage_key 不暴露给前端：前端拿到的是签名 URL（presigned）
"""

import enum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import BigInteger, Enum as SAEnum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document_chunk import DocumentChunk
    from app.models.knowledge_base import KnowledgeBase
    from app.models.tenant import Tenant
    from app.models.user import User


# ============================================================
# 业务枚举：文档处理状态
# ============================================================


class DocumentStatus(str, enum.Enum):
    """文档处理生命周期。

    流转：
        PENDING → PROCESSING → READY
                          ↘ FAILED
    """

    PENDING = "pending"      # 刚上传，等 Celery worker 拉
    PROCESSING = "processing"  # 正在解析/embedding
    READY = "ready"          # 完成，可以检索
    FAILED = "failed"        # 失败，看 error_message


# ============================================================
# SQLAlchemy 模型
# ============================================================


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """上传的文档元数据。

    ⚠️ 注意：原始文件存在 MinIO（对象存储），DB 只存路径和元信息。
    这样数据库不会因为存大文件而膨胀。
    """

    __tablename__ = "documents"

    # ---------- 业务字段 ----------

    # 租户 ID（冗余存，便于按租户过滤时不用 join）
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 属于哪个知识库
    knowledge_base_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 原始文件名
    filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # MIME type，比如 application/pdf
    content_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    # 文件大小（字节）
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    # MinIO 里的对象 key，比如 "tenants/{tenant_id}/kb/{kb_id}/docs/{doc_id}.pdf"
    # ⚠️ 安全：前端拿不到这个 key，只能拿后端签发的临时 URL
    storage_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        unique=True,  # 同一文件不能被存两次（防重）
    )

    # 处理状态
    status: Mapped[DocumentStatus] = mapped_column(
        SAEnum(DocumentStatus, name="document_status"),
        default=DocumentStatus.PENDING,
        nullable=False,
        index=True,  # "列出所有 PENDING 的文档给 worker" 用
    )

    # 失败原因（status=FAILED 时填）
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # 切了多少个 chunk（处理完才更新）
    chunk_count: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # 上传者
    # SET NULL：上传者被删，文档还在
    uploaded_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ---------- 关系（Relationships）----------

    # 多对一：属于某个 KB
    knowledge_base: Mapped["KnowledgeBase"] = relationship(back_populates="documents")

    # 多对一：属于某个租户（不常用，主要给类型提示）
    tenant: Mapped["Tenant"] = relationship()

    # 多对一：上传者
    uploader: Mapped["User | None"] = relationship(
        foreign_keys=[uploaded_by],
    )

    # 一对多：文档的所有 chunks
    # cascade="all, delete-orphan"：文档删了，chunks 一起删
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )

    # ---------- 复合索引 ----------

    __table_args__ = (
        # KB 内按"最新上传"排序
        Index(
            "ix_documents_kb_created",
            "knowledge_base_id",
            "created_at",
        ),
        # 租户内按状态查（如"我有哪些 PENDING 的文档"）
        Index(
            "ix_documents_tenant_status",
            "tenant_id",
            "status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Document tenant={self.tenant_id} filename={self.filename!r} status={self.status.value}>"
