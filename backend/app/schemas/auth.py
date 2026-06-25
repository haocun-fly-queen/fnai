"""Pydantic schemas for authentication endpoints."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# -------- Registration --------


class RegisterRequest(BaseModel):
    """User registration payload."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)
    tenant_name: str = Field(
        min_length=1, max_length=200, description="Workspace/tenant name to create"
    )
    tenant_slug: str | None = Field(
        default=None,
        min_length=2,
        max_length=60,
        pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$",
        description="URL-safe workspace id; auto-generated from tenant_name if omitted",
    )


# -------- Login --------


class LoginRequest(BaseModel):
    """User login payload."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


# -------- Tokens --------


class TokenPair(BaseModel):
    """Access + refresh token pair returned on login/register."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds")


class AccessTokenResponse(BaseModel):
    """Response when refreshing an access token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


# -------- User payload --------


class UserPublic(BaseModel):
    """Public user representation (never exposes password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    full_name: str
    status: str
    is_superuser: bool
    created_at: datetime
    last_login_at: datetime | None = None


class TenantPublic(BaseModel):
    """Public tenant representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    plan: str
    status: str
    created_at: datetime


class MembershipPublic(BaseModel):
    """Public tenant-membership representation."""

    model_config = ConfigDict(from_attributes=True)

    tenant: TenantPublic
    role: str


class CurrentUserResponse(BaseModel):
    """Response of GET /auth/me — user + tenants they belong to."""

    user: UserPublic
    memberships: list[MembershipPublic]
