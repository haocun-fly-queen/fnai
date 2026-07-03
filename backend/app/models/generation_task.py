"""GenerationTask — 文章生成任务表。

业务背景：
    AI 生成一篇文章要走 4 阶段管线（outline → section → seo → quality），
    每阶段都要调一次 LLM，整体可能 30-90 秒。
    这张表记录"一次生成任务的全过程"：进度、当前阶段、产物、错误等。

    一篇文章可以有多次生成任务（用户不满意点"重新生成"），
    所以 article ↔ generation_task 是一对多。

    虽然 V1 我们选择**同步返回**（用户等待 HTTP 响应），
    但仍把任务状态落库——为了：
      1. 后端可观测（哪个阶段慢、失败、token 用了多少）
      2. 给未来的 SSE / 后台任务化保留扩展点

数据模型：

    ┌─────────────────────────────────────────────┐
    │           generation_tasks 表                │
    ├─────────────────────────────────────────────┤
    │ id (UUID PK)                                 │
    │ article_id (FK → articles)                   │
    │ tenant_id (FK → tenants)                     │
    │ status (PG ENUM)                             │  ← 整体状态
    │ current_stage (PG ENUM, nullable)            │  ← 当前在哪个阶段
    │ params (jsonb)                               │  ← 生成参数快照(topic/kb_id/template/word_count)
    │ stage_logs (jsonb)                           │  ← 各阶段耗时/token/输出片段
    │ error_message (text, nullable)               │
    │ total_tokens (int, default 0)                │  ← 累计 token 用量
    │ started_at (datetime, nullable)              │
    │ finished_at (datetime, nullable)             │
    │ created_by (FK → users)                      │
    │ created_at / updated_at (mixin)              │
    └─────────────────────────────────────────────┘
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.article import Article
    from app.models.tenant import Tenant
    from app.models.user import User


class GenerationStatus(str, enum.Enum):
    """生成任务整体状态。"""

    PENDING = "pending"          # 已创建，未开始（V1 实际不太用，同步立刻进 RUNNING）
    RUNNING = "running"          # 正在跑某个阶段
    SUCCEEDED = "succeeded"      # 4 阶段全过
    FAILED = "failed"            # 某阶段炸了


class GenerationStage(str, enum.Enum):
    """4 阶段管线的阶段标识。"""

    OUTLINE = "outline"          # 1. 生成大纲
    SECTION = "section"          # 2. 按大纲写正文
    SEO = "seo"                  # 3. 生成 SEO 元信息
    QUALITY = "quality"          # 4. 质量检查/润色


class GenerationTask(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """一次文章生成任务的全过程记录。"""

    __tablename__ = "generation_tasks"

    # ---------- 关联 ----------

    article_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("articles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ---------- 状态 ----------

    status: Mapped[GenerationStatus] = mapped_column(
        SAEnum(GenerationStatus, name="generation_status"),
        default=GenerationStatus.PENDING,
        nullable=False,
        index=True,
    )

    # 当前在哪个阶段（status=RUNNING 时有意义，结束后保留作为"卡在哪步"的痕迹）
    current_stage: Mapped[GenerationStage | None] = mapped_column(
        SAEnum(GenerationStage, name="generation_stage"),
        nullable=True,
    )

    # ---------- 参数与日志 ----------

    # 生成参数快照（topic / knowledge_base_id / template_code / target_word_count / ...）
    params: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict,
    )

    # 各阶段日志：[{"stage": "outline", "duration_ms": 1234, "tokens": 567, "ok": true}, ...]
    stage_logs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list,
    )

    # 失败原因（status=FAILED 时填）
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 累计 token 用量（4 个阶段加起来）
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---------- 时间戳 ----------

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # ---------- 创建者 ----------

    created_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ---------- 关系 ----------

    article: Mapped["Article"] = relationship(back_populates="generation_tasks")
    tenant: Mapped["Tenant"] = relationship()
    creator: Mapped["User | None"] = relationship(foreign_keys=[created_by])

    # ---------- 索引 ----------

    __table_args__ = (
        # 查"某文章的最近一次生成"
        Index("ix_generation_tasks_article_created", "article_id", "created_at"),
        # 查"租户内正在跑的任务"（监控）
        Index("ix_generation_tasks_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<GenerationTask article={self.article_id} status={self.status.value}>"
