"""Tenant model — represents a workspace/organization.

A tenant is the top-level isolation unit. Users belong to one or more tenants
via TenantMember. All business data (knowledge bases, articles) is scoped
to a tenant via tenant_id.
"""

from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.invitation import Invitation
    from app.models.membership import TenantMember


class TenantPlan(str, PyEnum):
    """Subscription tier. Drives feature flags + rate limits."""

    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class TenantStatus(str, PyEnum):
    """Lifecycle state. Inactive tenants cannot log in."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class Tenant(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    plan: Mapped[TenantPlan] = mapped_column(
        Enum(TenantPlan, name="tenant_plan"),
        default=TenantPlan.FREE,
        nullable=False,
    )
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"),
        default=TenantStatus.ACTIVE,
        nullable=False,
    )

    # Relationships
    members: Mapped[list["TenantMember"]] = relationship(
        back_populates="tenant",
        cascade="all, delete-orphan",
    )

    # 邀请列表：租户被删时邀请一起删（CASCADE 已在 FK 上）
    # 这里不加 cascade，因为 Invitation 有自己的 FK CASCADE
    invitations: Mapped[list["Invitation"]] = relationship(
        back_populates="tenant",
    )

    def __repr__(self) -> str:
        return f"<Tenant {self.slug} ({self.plan.value})>"
