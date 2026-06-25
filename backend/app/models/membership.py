"""TenantMember — many-to-many between User and Tenant, with a Role.

A user can belong to multiple tenants (consultant across agencies).
The role is per-tenant (you can be admin in tenant A, viewer in tenant B).
"""

from enum import Enum as PyEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


class Role(str, PyEnum):
    """Per-tenant role. Drives authorization checks."""

    OWNER = "owner"  # Tenant creator; cannot be removed
    ADMIN = "admin"  # Manage members, settings
    MEMBER = "member"  # Create/edit content
    VIEWER = "viewer"  # Read-only


class TenantMember(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "tenant_members"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_tenant_members_user_tenant"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[Role] = mapped_column(
        SAEnum(Role, name="tenant_member_role"),
        default=Role.MEMBER,
        nullable=False,
    )
    invited_by: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    # user_id is the *primary* join side (this is the member). invited_by is
    # a separate FK back to users; we don't expose it as a collection.
    user: Mapped["User"] = relationship(
        back_populates="memberships",
        foreign_keys=[user_id],
    )
    tenant: Mapped["Tenant"] = relationship(back_populates="members")

    def __repr__(self) -> str:
        return f"<TenantMember user={self.user_id} tenant={self.tenant_id} role={self.role.value}>"
