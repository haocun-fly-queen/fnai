"""DocumentChunk — 文档分片 + 向量表。

业务背景：
    文档太长了（PDF 可能几百页），没法直接送给 LLM/embedding。
    拆成"小段"（chunk），每段独立算 embedding，检索时也是按段匹配。

    存储结构：
        - 原始文本（content）
        - 位置信息（chunk_index, char_start, char_end）→ 检索时能跳回原文
        - 向量（embedding）→ pgvector 列，1536 维（OpenAI text-embedding-3-small）

数据模型（给 Java 同事的提示 ≈ @Entity + @Table）：

    ┌────────────────────────────────────────┐
    │        document_chunks 表               │
    ├────────────────────────────────────────┤
    │ id (UUID PK)                            │
    │ tenant_id (FK → tenants)                │  ← 冗余存（为了按租户过滤时不用 join documents）
    │ knowledge_base_id (FK → knowledge_bases)│  ← 冗余存（同上）
    │ document_id (FK → documents)            │
    │ chunk_index (int)                       │  ← 在文档里的第几段（从 0 开始）
    │ content (text)                          │  ← 原始文本内容
    │ content_length (int)                    │  ← 字符数（方便过滤太短的 chunk）
    │ char_start / char_end (int)             │  ← 在原文中的位置
    │ embedding (vector(1536))                │  ← 关键！pgvector 列
    │ created_at / updated_at (mixin)         │
    └────────────────────────────────────────┘

⚠️ pgvector 关键点：
    - 必须先在 DB 里 CREATE EXTENSION vector; 才能用 vector() 类型
    - vector(N) 中 N 是维度，必须跟 embedding 模型输出对得上
    - OpenAI text-embedding-3-small = 1536 维
    - 查询用 cosine_distance (1 - cosine similarity)
    - 用 ivfflat 索引加速（适合百万级以下数据量）

⚠️ 设计要点：
    - tenant_id + knowledge_base_id 冗余存：检索时常用"这个 KB 下的所有 chunks"
      不冗余就要 join documents，性能差
    - chunk_index 在 document_id 内唯一（同一文档段号不能重）
    - embedding 列允许 NULL：处理中还没算出来时
"""

from typing import TYPE_CHECKING
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.knowledge_base import KnowledgeBase
    from app.models.tenant import Tenant


# embedding 维度从 config 读
# text-embedding-3-small = 1536
# text-embedding-3-large = 3072
EMBEDDING_DIM = settings.embedding_dim  # type: ignore[attr-defined]


class DocumentChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """文档分片（带 embedding 向量）。

    ⚠️ 这是知识库的"核心数据"——RAG 检索就是查这张表。
    """

    __tablename__ = "document_chunks"

    # ---------- 业务字段 ----------

    # 租户 ID（冗余存，检索时按租户过滤不用 join）
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 知识库 ID（冗余存，常见查询："这个 KB 的所有 chunk"）
    knowledge_base_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 属于哪个文档
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 在文档里的段号（从 0 开始）
    chunk_index: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 原始文本内容
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    # 字符数（冗余存，省得每次 LENGTH(content)）
    content_length: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # 在原文中的字符位置（方便前端高亮定位）
    char_start: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    char_end: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # ⚠️ 关键：embedding 向量
    # 维度从 config 读（默认 1536）
    # nullable=True：处理中还没算出来时
    embedding = mapped_column(
        Vector(EMBEDDING_DIM),
        nullable=True,
    )

    # ---------- 关系（Relationships）----------

    # 多对一：属于某个文档
    document: Mapped["Document"] = relationship(back_populates="chunks")

    # 多对一：属于某个 KB
    knowledge_base: Mapped["KnowledgeBase"] = relationship()

    # 多对一：属于某个租户（类型提示用）
    tenant: Mapped["Tenant"] = relationship()

    # ---------- 复合索引 ----------

    __table_args__ = (
        # 同一文档内 chunk_index 不能重
        Index(
            "uq_document_chunks_doc_index",
            "document_id",
            "chunk_index",
            unique=True,
        ),
        # 租户 + KB 内的 chunk 检索
        Index(
            "ix_document_chunks_tenant_kb",
            "tenant_id",
            "knowledge_base_id",
        ),
        # 字符范围必须合法
        CheckConstraint(
            "char_end > char_start",
            name="ck_document_chunks_char_range",
        ),
        CheckConstraint(
            "content_length > 0",
            name="ck_document_chunks_content_length",
        ),
        CheckConstraint(
            "chunk_index >= 0",
            name="ck_document_chunks_index_nonneg",
        ),
        # ⚠️ pgvector 的 ivfflat 索引（向量相似度搜索用）
        # 条件：只在 embedding 不为 NULL 时建
        # lists = 100 适合 10万~100万 行的数据量
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_where=embedding.isnot(None),  # type: ignore[attr-defined]
        ),
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk doc={self.document_id} idx={self.chunk_index} len={self.content_length}>"
