"""Invitation HTTP 端点。

本文件是邀请流程的 HTTP 入口，4 个端点：

    POST   /invitations         创建一个新邀请（OWNER/ADMIN 权限）
    GET    /invitations         列出当前租户的所有邀请（OWNER/ADMIN 权限）
    POST   /invitations/accept  接受邀请（任何登录用户）
    DELETE /invitations/{id}    撤销一个 pending 邀请（OWNER/ADMIN 权限）

学习要点（给 Java 背景的同事）：
- 端点 = Spring 的 @RestController 方法
- 端点"瘦"：只接参、调 service、翻译异常
- 鉴权/授权完全靠 Depends(require_role(...)) 装饰（工厂函数）
- 业务异常用 InvitationError，端点 catch 后翻译成 HTTPException
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.membership import Role, TenantMember
from app.models.user import User
from app.schemas.invitation import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    CreateInvitationRequest,
    InvitationCreateResponse,
    InvitationPublic,
    ListInvitationsResponse,
)
from app.services import invitation as invitation_service
from app.services.invitation import InvitationError

# ============================================================
# 路由配置
# ============================================================
# prefix="/invitations" → 所有路径以 /api/v1/invitations 开头
# tags=["invitations"] → Swagger UI 按 tag 分组
router = APIRouter(prefix="/invitations", tags=["invitations"])


# ============================================================
# 工具函数：把业务异常翻译成 HTTP 异常
# ============================================================


def _invitation_error_to_http(err: InvitationError) -> HTTPException:
    """把 InvitationError 翻译成合适的 HTTP 状态码。

    错误码 → HTTP 状态码的映射：
      - 4xx 客户端错（参数错、未授权、资源冲突）
      - 5xx 服务端错（理论上不该出现）

    设计原则：
    - 不同的业务错误给不同的状态码 + 不同的 code 字段
    - 前端可以根据 code 做不同 UX（"已过期" vs "链接无效"）
    """
    code = err.code

    # ---------- 404 资源不存在 ----------
    if code in ("token_not_found", "invitation_not_found", "tenant_not_found"):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": code, "message": err.message},
        )

    # ---------- 410 Gone（资源已不可用）----------
    if code in ("token_expired",):
        return HTTPException(
            status_code=status.HTTP_410_GONE,
            detail={"code": code, "message": err.message},
        )

    # ---------- 403 禁止访问 ----------
    if code in (
        "token_revoked",  # 邀请被撤销
        "email_mismatch",  # 邮箱不一致
        "cannot_invite_owner",  # 不能通过邀请给 OWNER
        "wrong_tenant",  # 邀请不属于当前租户
    ):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": code, "message": err.message},
        )

    # ---------- 409 状态冲突 ----------
    if code in (
        "token_used",  # 邀请已被接受
        "token_used_race",  # 并发：刚刚被其他请求接受
        "duplicate_pending_invitation",  # 已有同 email 的 pending 邀请
        "already_accepted",  # 已接受不能撤销
        "already_a_member",  # 已经是成员
        "tenant_inactive",  # 租户被停用
    ):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": code, "message": err.message},
        )

    # ---------- 400 兜底 ----------
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": err.message},
    )


# ============================================================
# 端点 1：创建邀请
# ============================================================


@router.post(
    "",
    response_model=InvitationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new invitation (OWNER/ADMIN only)",
)
async def create_invitation(
    payload: CreateInvitationRequest,
    request: Request,  # 用来拿 host/port 拼完整 URL
    # 鉴权：必须登录
    current_user: Annotated[User, Depends(get_current_user)],
    # 授权：必须是 MEMBER 及以上（OWNER/ADMIN/MEMBER 都能邀请）
    # ⚠️ 业务约束：实际我们只让 ADMIN/OWNER 邀请
    # 所以这里用 require_role(Role.ADMIN)
    # 但如果产品想放宽到 MEMBER，把 ADMIN 改成 MEMBER 即可
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationCreateResponse:
    """POST /api/v1/invitations

    创建一个新的邀请记录。

    业务约束：
    - 必须 OWNER/ADMIN 才能创建邀请（require_role 装饰器强制）
    - 角色不能是 OWNER（service 校验）
    - 同一 email 同一租户只能有一个 pending 邀请（partial unique index 强制）

    Returns:
        包含 invitation 记录 + 完整 URL + 纯 token
        前端用完整 URL 复制发出去（邮件、IM、二维码等）
    """
    try:
        inv, invite_link = await invitation_service.create_invitation(
            db,
            tenant_id=membership.tenant_id,
            invited_by=current_user.id,
            email=payload.email,
            role=payload.role,
            request=request,
        )
    except InvitationError as exc:
        raise _invitation_error_to_http(exc) from exc

    return InvitationCreateResponse(
        invitation=InvitationPublic.model_validate(inv),
        invite_link=invite_link,
        token=inv.token,
    )


# ============================================================
# 端点 2：列出当前租户的邀请
# ============================================================


@router.get(
    "",
    response_model=ListInvitationsResponse,
    summary="List invitations for the current tenant (OWNER/ADMIN only)",
)
async def list_invitations(
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ListInvitationsResponse:
    """GET /api/v1/invitations

    列出当前租户的所有邀请（pending + 历史），按创建时间倒序。

    业务用途：团队管理页"成员邀请"列表。
    """
    result = await invitation_service.list_invitations(
        db,
        tenant_id=membership.tenant_id,
    )
    return ListInvitationsResponse(
        items=[InvitationPublic.model_validate(item) for item in result["items"]],
        active_tenant_id=membership.tenant_id,
        pending_count=result["pending_count"],
        accepted_count=result["accepted_count"],
    )


# ============================================================
# 端点 3：接受邀请
# ============================================================


@router.post(
    "/accept",
    response_model=AcceptInvitationResponse,
    summary="Accept an invitation (any logged-in user)",
)
async def accept_invitation(
    payload: AcceptInvitationRequest,
    # ⚠️ 任何登录用户都能接受（不要求是租户成员）
    # 但 service 层会校验 email 一致性
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AcceptInvitationResponse:
    """POST /api/v1/invitations/accept

    用 token 接受邀请，加入对应租户。

    业务校验（service 层）：
    1. token 存在、未过期、未使用、未撤销
    2. 当前用户 email == invitation.email（防被偷链接）
    3. 当前用户还不是该租户成员

    接受成功后：
    - 创建 TenantMember 行
    - 标记 invitation 为 accepted
    - 返回新租户信息
    """
    try:
        result = await invitation_service.accept_invitation(
            db,
            token=payload.token,
            current_user=current_user,
        )
    except InvitationError as exc:
        raise _invitation_error_to_http(exc) from exc

    return AcceptInvitationResponse(
        invitation=InvitationPublic.model_validate(result["invitation"]),
        joined_tenant=result["joined_tenant"],
        message="Invitation accepted successfully",
    )


# ============================================================
# 端点 4：撤销邀请
# ============================================================


@router.delete(
    "/{invitation_id}",
    response_model=InvitationPublic,
    summary="Revoke a pending invitation (OWNER/ADMIN only)",
)
async def revoke_invitation(
    invitation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationPublic:
    """DELETE /api/v1/invitations/{invitation_id}

    撤销一个 pending 邀请。

    业务校验：
    - 只有 OWNER/ADMIN 能撤销
    - 邀请必须属于当前租户
    - 已接受的不能撤销（要走"踢人"接口）
    """
    try:
        inv = await invitation_service.revoke_invitation(
            db,
            invitation_id=invitation_id,
            current_user=current_user,
            current_tenant_id=membership.tenant_id,
        )
    except InvitationError as exc:
        raise _invitation_error_to_http(exc) from exc

    return InvitationPublic.model_validate(inv)
