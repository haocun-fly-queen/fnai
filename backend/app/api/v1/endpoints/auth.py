"""Auth endpoints: register, login, refresh, current-user."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.core.security import create_access_token, decode_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    CurrentUserResponse,
    LoginRequest,
    MembershipPublic,
    RegisterRequest,
    TenantPublic,
    TokenPair,
    UserPublic,
)
from app.services import auth as auth_service
from app.services.auth import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])


def _auth_error_to_http(err: AuthError) -> HTTPException:
    """Translate domain errors into HTTP exceptions.

    Status codes:
    - email_taken / duplicate → 409 Conflict
    - account_disabled → 403 Forbidden
    - everything else (invalid_credentials, user_not_found) → 401 Unauthorized
    """
    code = err.code
    if code in ("email_taken",):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail={"code": code, "message": err.message}
        )
    if code in ("account_disabled",):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail={"code": code, "message": err.message}
        )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": code, "message": err.message}
    )


@router.post(
    "/register",
    response_model=CurrentUserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user and create their first tenant",
)
async def register(
    payload: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    response: Response,  # type: ignore[type-arg]
) -> CurrentUserResponse:
    try:
        result = await auth_service.register(
            db,
            email=payload.email,
            password=payload.password,
            full_name=payload.full_name,
            tenant_name=payload.tenant_name,
            tenant_slug=payload.tenant_slug,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc

    # Tokens are returned in response headers; the body is just the user.
    response.headers["X-Access-Token"] = result["access_token"]
    response.headers["X-Refresh-Token"] = result["refresh_token"]
    response.headers["X-Token-Type"] = "bearer"
    response.headers["X-Expires-In"] = "900"

    user = result["user"]
    memberships = [
        MembershipPublic(
            tenant=TenantPublic.model_validate(m.tenant),
            role=m.role.value,
        )
        for m in user.memberships
    ]
    return CurrentUserResponse(
        user=UserPublic.model_validate(user),
        memberships=memberships,
    )


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Authenticate and receive an access + refresh token pair",
)
async def login(
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    try:
        _user, access, refresh = await auth_service.login(
            db,
            email=payload.email,
            password=payload.password,
        )
    except AuthError as exc:
        raise _auth_error_to_http(exc) from exc
    return TokenPair(access_token=access, refresh_token=refresh, expires_in=60 * 15)


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    summary="Exchange a refresh token for a new access token",
)
async def refresh_token(
    payload: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AccessTokenResponse:
    """Body: ``{"refresh_token": "<jwt>"}``. Issues a new access token only."""
    token = payload.get("refresh_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "missing_refresh_token", "message": "refresh_token is required"},
        )
    try:
        claims = decode_token(token, expected_type="refresh")
        user_id = claims["sub"]
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_refresh_token", "message": str(exc)},
        ) from exc

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "user_not_found", "message": "User no longer exists"},
        )

    # 刷新 token 时也要带上 active_tenant_id
    # 否则前端用新 access token 请求业务接口时会丢失"当前租户"上下文
    # 这里我们用"用户默认租户"（同 login 逻辑），简单起见
    from app.services.tenant import get_default_tenant_for_user  # 局部 import 避免循环

    default_membership = await get_default_tenant_for_user(db, user.id)
    active_tenant_id = default_membership.tenant_id if default_membership else None

    new_access = create_access_token(user.id, active_tenant_id=active_tenant_id)
    return AccessTokenResponse(access_token=new_access, expires_in=60 * 15)


@router.get(
    "/me",
    response_model=CurrentUserResponse,
    summary="Get the currently authenticated user with their tenant memberships",
)
async def me(
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CurrentUserResponse:
    user, memberships = await auth_service.get_user_with_memberships(db, current.id)
    return CurrentUserResponse(
        user=UserPublic.model_validate(user),
        memberships=[
            MembershipPublic(
                tenant=TenantPublic.model_validate(m.tenant),
                role=m.role.value,
            )
            for m in memberships
        ],
    )
