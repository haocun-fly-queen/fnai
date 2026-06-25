"""User model — global identity.

A user is a person (one human, one account). They can belong to multiple
tenants via TenantMember. The email is globally unique (login key).
"""

from datetime import datetime
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.membership import TenantMember


class UserStatus(str, PyEnum):
    """Account lifecycle. Suspended users cannot authenticate."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        String(20),
        default=UserStatus.ACTIVE.value,
        nullable=False,
    )
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    # NOTE: TenantMember has TWO FKs back to users (user_id, invited_by).
    # We must disambiguate which one drives the back-populates for the
    # `memberships` collection. We pick user_id as the primary side.
    memberships: Mapped[list["TenantMember"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="TenantMember.user_id",
    )

    def __repr__(self) -> str:
        return f"<User {self.email}>"
