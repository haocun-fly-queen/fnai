"""Invitation — 邀请用户加入租户的中间表。

业务背景：
    在多租户 SaaS 里，不能让用户"自己加入"租户（那等于能进任何工作空间）。
    必须有"现任成员主动邀请"这个动作，这就是 invitation 表的用途。

    流程：
    1. 苏苏（OWNER）填李雷的 email + 选角色（MEMBER），点"邀请"
    2. 后端生成一个一次性 token 存到 invitation 表，发链接给李雷
    3. 李雷点链接 → 后端校验 token 没过期+没用过 → 把李雷加进 tenant_members
    4. 李雷登录后 dashboard 就能看到新工作空间

为什么不用 "users 表加一个 invited_by 字段"：
    - 邀请是"待办"不是"完成"，需要状态（pending/accepted/expired/revoked）
    - 一个 email 可以被多次邀请（每次新 token）
    - 邀请是有时间限制的（7 天过期）
    - 接受后才生成 tenant_members 行，未接受的不应该污染成员表

数据模型设计（给 Java 同事的提示 ≈ Java 的 @Entity + @Table）：

    ┌────────────────────────────────────────┐
    │            Invitation 表                │
    ├────────────────────────────────────────┤
    │ id (UUID PK)                            │
    │ tenant_id (FK → tenants)                │
    │ email (varchar)                         │  ← 被邀请者邮箱（未注册也行）
    │ role (PG ENUM)                          │  ← 接受后给什么角色
    │ token (varchar, unique)                 │  ← 一次性 token
    │ invited_by (FK → users)                 │  ← 邀请人
    │ expires_at (timestamptz)                │  ← 7 天后过期
    │ accepted_at (timestamptz, nullable)     │  ← 接受时间（null = 未接受）
    │ created_at / updated_at (mixin)         │
    └────────────────────────────────────────┘

复合唯一约束（重要）：
    - (tenant_id, email) 上 partial unique index WHERE accepted_at IS NULL
      防止"同一租户对同一邮箱有多个待接受邀请"（同一时刻只有一个）
      但允许"历史接受过 + 又有新邀请" 的情况（因为有部分索引）
"""

from datetime import datetime, timedelta, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.membership import Role

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


# ============================================================
# 业务枚举：邀请的状态
# ============================================================


class InvitationStatus(str, PyEnum):
    """邀请生命周期状态。

    PENDING  → 刚创建，等被邀请者点链接
    ACCEPTED → 已被接受（accepted_at 有值）
    EXPIRED  → 过期了（expires_at < now()，每次查询时计算）
    REVOKED  → 邀请人主动撤销

    注意：EXPIRED 是"派生状态"，不在 DB 里存一个 status 列。
    每次查的时候根据 expires_at 算出来。
    这样省一个字段、也避免"忘记更新状态"的 bug。

    ⚠️ 这是个"行为驱动"的枚举——它对应的是查询时的过滤条件，
    不是一个真正存在表里的字段。
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


# ============================================================
# SQLAlchemy 模型
# ============================================================


class Invitation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """邀请记录。

    ⚠️ 重要：这张表只存"待处理/历史"的邀请，
    一旦接受，tenant_members 会多一行；invitation 这行不会删。
    原因：审计/合规要求"谁在什么时候被邀请的、什么时候接受的"。
    """

    __tablename__ = "invitations"

    # ---------- 业务字段 ----------

    # 邀请到哪个租户
    # CASCADE：租户被删时，邀请一起删（没意义了）
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 被邀请者邮箱
    # 注意：不要 FK 到 users.id，因为被邀请者**不一定已注册**
    # 业务场景：先邀请，注册时自动匹配这个 email
    email: Mapped[str] = mapped_column(
        String(254),  # RFC 5321 规定 email 最长 254
        nullable=False,
        # 普通索引（不是 unique）：同 email 可以被不同租户邀请
        index=True,
    )

    # 接受后给什么角色
    # 用 Role 枚举：OWNER/ADMIN/MEMBER/VIEWER
    # ⚠️ 安全：业务上不允许通过邀请给 OWNER（会绕过"创建者就是 OWNER"的安全模型）
    # 这个校验在 service 层做（不允许 Role.OWNER 通过邀请分配）
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="tenant_member_role"),
        nullable=False,
    )

    # 一次性 token
    # ⚠️ 安全：必须 unique（数据库级别防重复）+ 用 secrets 生成（不可猜）
    # 256 位熵 = 32 字节 base64 = 43 字符
    token: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    # 邀请人
    # SET NULL：邀请人账号被删了，邀请记录还在（不级联）
    invited_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 过期时间
    # 默认 7 天后过期
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # 接受时间（null = 未接受）
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # 撤销时间（null = 未撤销）
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ---------- 关系（Relationships）----------

    # 多对一：邀请属于某个租户
    tenant: Mapped["Tenant"] = relationship(back_populates="invitations")

    # 多对一：邀请人（可能为空，邀请人账号被删时）
    inviter: Mapped["User | None"] = relationship(
        foreign_keys=[invited_by],
        # 不用 back_populates，因为 User 模型上没"我发出的邀请"集合
        # （避免一个用户发出 N 个邀请时加载 N 个对象）
    )

    # ---------- 复合索引 ----------

    __table_args__ = (
        # 复合唯一索引：同一租户对同一邮箱，只能有一个"未处理"的邀请
        # 用 partial unique index（WHERE accepted_at IS NULL AND revoked_at IS NULL）
        # 这样：
        #   - 接受后可以再发新邀请
        #   - 撤销后可以再发新邀请
        #   - 但同一时刻只能有一个"活的"邀请
        Index(
            "uq_invitations_tenant_email_active",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL AND revoked_at IS NULL"),
        ),
    )

    # ---------- 业务方法 ----------

    def is_expired(self, now: datetime | None = None) -> bool:
        """判断这个邀请是否过期。"""
        if now is None:
            now = datetime.now(tz=timezone.utc)
        return self.expires_at <= now

    def is_active(self, now: datetime | None = None) -> bool:
        """判断这个邀请是否"还可以被接受"。

        条件：未接受 + 未撤销 + 未过期
        """
        return self.accepted_at is None and self.revoked_at is None and not self.is_expired(now)

    @property
    def status(self) -> InvitationStatus:
        """派生状态：每次取实时算。"""
        if self.accepted_at is not None:
            return InvitationStatus.ACCEPTED
        if self.revoked_at is not None:
            return InvitationStatus.REVOKED
        if self.is_expired():
            return InvitationStatus.EXPIRED
        return InvitationStatus.PENDING

    def __repr__(self) -> str:
        return f"<Invitation tenant={self.tenant_id} email={self.email} role={self.role.value} status={self.status.value}>"


# ============================================================
# 工厂函数：创建带默认过期时间的邀请
# ============================================================


def make_invitation(
    *,
    tenant_id: UUID,
    email: str,
    role: Role,
    invited_by: UUID,
    token: str,
    ttl_days: int = 7,
) -> Invitation:
    """工厂函数：建一个带默认 7 天过期的邀请实例。

    为什么是工厂函数而不是直接 Invitation(...)？
    - 把"过期时间 = now + 7 days"这个默认值集中管理
    - service 层不用关心时区、不用关心 ttl 计算
    - 单元测试时容易 mock（传固定 now）

    Args:
        tenant_id: 目标租户
        email: 被邀请者邮箱
        role: 给什么角色
        invited_by: 邀请人 user_id
        token: 已生成的 token（service 层用 secrets 生成的）
        ttl_days: 几天后过期，默认 7

    Returns:
        Invitation 实例（**还没 add 到 session**）
    """
    now = datetime.now(tz=timezone.utc)
    return Invitation(
        tenant_id=tenant_id,
        email=email.lower(),  # ⚠️ 统一小写，避免 "Bob@x.com" 和 "bob@x.com" 算两个
        role=role,
        invited_by=invited_by,
        token=token,
        expires_at=now + timedelta(days=ttl_days),
    )
