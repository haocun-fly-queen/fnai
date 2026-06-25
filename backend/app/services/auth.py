"""Auth business logic: register, login, refresh.

Layered between FastAPI endpoints and the database. Endpoints stay thin;
all the side effects (tenant creation, role assignment, etc.) live here.
"""

import re
from typing import Any, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models.membership import Role, TenantMember
from app.models.tenant import Tenant
from app.models.user import User, UserStatus
from app.services.tenant import get_default_tenant_for_user  # 新增 import


class AuthError(Exception):
    """Domain-level auth error. Endpoints translate to 400/401/409."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _slugify(name: str) -> str:
    """Generate a URL-safe slug from a tenant name. Falls back to 'tenant'."""
    base = name.lower().strip()
    base = _SLUG_RE.sub("-", base).strip("-")
    return base or "tenant"


async def register(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    tenant_name: str,
    tenant_slug: str | None,
) -> dict[str, Any]:
    """Register a new user and create their first tenant.

    Returns a dict with: user, tenant, membership, access_token, refresh_token.
    The caller is responsible for shaping the API response.
    """
    # 1. Reject duplicate email early.
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise AuthError("email_taken", "Email is already registered")

    # 2. Reserve the slug. If user didn't provide one, derive from name.
    base_slug = tenant_slug or _slugify(tenant_name)
    slug = base_slug
    suffix = 0
    while await db.scalar(select(Tenant).where(Tenant.slug == slug)) is not None:
        suffix += 1
        slug = f"{base_slug}-{suffix}"

    # 3. Create user, tenant, membership in a single transaction.
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    try:
        await db.flush()  # populate user.id
    except IntegrityError as exc:
        await db.rollback()
        raise AuthError("email_taken", "Email is already registered") from exc

    tenant = Tenant(name=tenant_name, slug=slug)
    db.add(tenant)
    await db.flush()  # populate tenant.id

    membership = TenantMember(
        user_id=user.id,
        tenant_id=tenant.id,
        role=Role.OWNER,
    )
    db.add(membership)

    # 关键：检查这个 email 是不是有 pending 邀请
    # 如果有 → 自动接受，让用户注册完直接看到新工作空间
    # ⚠️ 必须在 commit 前调用（同一个事务里）
    from app.services.invitation import auto_accept_pending_for_new_user

    await auto_accept_pending_for_new_user(db, user=user)

    await db.commit()
    # Eager-load memberships WITH the related tenant while the session is
    # still alive — this is the data we'll serialize into the response.
    user = await db.scalar(
        select(User)
        .where(User.id == user.id)
        .options(selectinload(User.memberships).selectinload(TenantMember.tenant))
    )
    membership = next((m for m in user.memberships if m.tenant_id == tenant.id), None)

    logger.info("user.registered", user_id=str(user.id), tenant_id=str(tenant.id))

    # 关键：把新建的 tenant_id 设为 active_tenant_id
    # 这样用户注册成功后访问业务接口时，能直接落到刚创建的租户下
    access = create_access_token(user.id, active_tenant_id=tenant.id)
    refresh = create_refresh_token(user.id)
    return {
        "user": user,
        "tenant": tenant,
        "membership": membership,
        "access_token": access,
        "refresh_token": refresh,
    }


async def login(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> tuple[User, str, str]:
    """Validate credentials and issue tokens."""
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        raise AuthError("invalid_credentials", "Email or password is incorrect")

    if user.status != UserStatus.ACTIVE:
        raise AuthError("account_disabled", "Account is disabled or pending verification")

    # 登录时自动选一个默认激活租户
    # 策略：用户是 OWNER 的租户优先，否则最近加入的
    # 这样老用户登录后会"自动回到上次的工作空间"（简化的实现）
    default_membership = await get_default_tenant_for_user(db, user.id)
    active_tenant_id = default_membership.tenant_id if default_membership else None

    access = create_access_token(user.id, active_tenant_id=active_tenant_id)
    refresh = create_refresh_token(user.id)
    logger.info(
        "user.login",
        user_id=str(user.id),
        active_tenant_id=str(active_tenant_id) if active_tenant_id else None,
    )
    return user, access, refresh


async def get_user_with_memberships(
    db: AsyncSession,
    user_id: UUID,
) -> tuple[User, Sequence[TenantMember]]:
    """Load a user with all their tenant memberships eager-loaded."""
    user = await db.scalar(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.memberships).selectinload(TenantMember.tenant))
    )
    if user is None:
        raise AuthError("user_not_found", "User no longer exists")
    return user, user.memberships


def build_token_response(*, access_token: str, refresh_token: str) -> dict:
    """Build a uniform token response payload."""
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 60 * 15,  # mirrors access_token_expire_minutes
    }
