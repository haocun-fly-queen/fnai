"""ModelCallLog — LLM 调用日志表（成本审计 + 排查）。

业务背景：
    每次调 LLM（embedding 或 chat）都记一条日志。用途：
      1. 成本审计——这个月某租户烧了多少 token / 多少钱
      2. 排查——某次生成为什么失败、哪个 prompt 的输出有问题
      3. 数据回放——以后做 A/B 测试时能拿历史数据对比

    这张表会增长很快（每篇文章 4-N 条），所以：
      - 不存完整 prompt/response（太占空间），只存截断的前 1000 字
      - 提供按时间分区/归档的余地（V1 不做，靠后续 cleanup job）

数据模型：

    ┌─────────────────────────────────────────────┐
    │           model_call_logs 表                 │
    ├─────────────────────────────────────────────┤
    │ id (UUID PK)                                 │
    │ tenant_id (FK → tenants)                     │
    │ generation_task_id (FK, nullable)            │  ← 关联到哪次生成（NULL = 检索向量化等独立调用）
    │ purpose (varchar 50)                         │  ← "embedding" / "outline" / "section" / ...
    │ model (varchar 100)                          │  ← 实际用的模型名（qwen-plus / text-embedding-v2）
    │ prompt_preview (text)                        │  ← prompt 前 1000 字
    │ response_preview (text)                      │  ← 响应前 1000 字
    │ prompt_tokens / completion_tokens / total_tokens (int) │
    │ duration_ms (int)                            │
    │ ok (bool)                                    │  ← 调用是否成功
    │ error_message (text, nullable)               │
    │ created_at (datetime)                        │
    └─────────────────────────────────────────────┘

注意：这张表**只写不读**给业务用——读是给后台分析/账单看的。
"""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.generation_task import GenerationTask
    from app.models.tenant import Tenant


class ModelCallLog(Base, UUIDPrimaryKeyMixin):
    """LLM 调用日志（每次调 chat/embedding 都记一条）。"""

    __tablename__ = "model_call_logs"

    # ---------- 归属 ----------

    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 哪次生成任务触发的（独立调用如检索向量化，可以为 NULL）
    generation_task_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("generation_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ---------- 调用上下文 ----------

    # 用途标识："embedding" / "outline" / "section" / "seo" / "quality" / "search_query"
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)

    # 实际模型名
    model: Mapped[str] = mapped_column(String(100), nullable=False)

    # ---------- 截断的内容（防止表炸）----------

    prompt_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    response_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # ---------- 用量 / 性能 ----------

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # ---------- 状态 ----------

    ok: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---------- 时间 ----------

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ---------- 关系 ----------

    tenant: Mapped["Tenant"] = relationship()
    generation_task: Mapped["GenerationTask | None"] = relationship()

    # ---------- 索引 ----------

    __table_args__ = (
        # 按租户 + 时间查（成本审计常用）
        Index("ix_model_call_logs_tenant_created", "tenant_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<ModelCallLog purpose={self.purpose} tokens={self.total_tokens} ok={self.ok}>"
