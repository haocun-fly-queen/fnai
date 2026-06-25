"""Membership 管理 HTTP 端点：列成员、改角色、踢人。

学习要点（给 Java 背景的同事）：
- 3 个端点全是"管理类"，需要 ADMIN 权限
- 全部走 require_role(Role.ADMIN) 装饰器
- 业务异常用 MembershipError，端点 catch 后翻译成 HTTPException
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.membership import Role, TenantMember
from app.models.user import User
from app.schemas.membership import (
    ChangeRoleRequest,
    ChangeRoleResponse,
    ListMembersResponse,
    MemberDetail,
    RemoveMemberResponse,
)
from app.services import membership as membership_service
from app.services.membership import MembershipError

# 路由配置
# ⚠️ 这里 prefix 是空，因为路径已经在主 router 里拼了
# （在 __init__.py 里 include_router 时加 prefix="/tenants"）
router = APIRouter(tags=["memberships"])


# ============================================================
# 工具函数：业务异常 → HTTP 异常
# ============================================================


def _membership_error_to_http(err: MembershipError) -> HTTPException:
    """把 MembershipError 翻译成合适的 HTTP 状态码。"""
    code = err.code

    # ---------- 404 ----------
    if code == "member_not_found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": code, "message": err.message},
        )

    # ---------- 403 ----------
    if code in (
        "permission_denied",
        "self_role_change",
        "self_remove",
    ):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": code, "message": err.message},
        )

    # ---------- 409 ----------
    if code in (
        "cannot_assign_owner",
        "downgrade_last_owner",
        "remove_last_owner",
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
# 端点 1：列成员
# ============================================================


@router.get(
    "/tenants/{tenant_id}/members",
    response_model=ListMembersResponse,
    summary="List all members of a tenant",
)
async def list_members(
    tenant_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    # ⚠️ 任何成员都能看（不要求 ADMIN）
    # 因为 list 操作不修改数据，应该让 VIEWER 也能看
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ListMembersResponse:
    """GET /api/v1/tenants/{tenant_id}/members

    列出某租户的所有成员，按 role 等级倒序（OWNER 排前）。

    ⚠️ 当前租户检查：
    - 这里用 require_role(Role.VIEWER) 拿的是"当前激活租户"的 membership
    - 如果 tenant_id 和 active_tenant_id 不一致 → 检查会失败
    - 简化做法：只允许查自己 active 租户的成员
      （跨租户查询未来加）

    业务用途：团队管理页"当前成员"列表
    """
    # ⚠️ 安全检查：tenant_id 必须和当前激活租户一致
    # 不允许查其他租户的成员（虽然有 tenant_id 在 URL，但加上这层保护更稳）
    if tenant_id != membership.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "tenant_mismatch",
                "message": "Can only list members of your active tenant",
            },
        )

    items = await membership_service.list_members(
        db,
        tenant_id=tenant_id,
        current_user_id=current_user.id,
    )

    # 把 dict 转成 schema 列表（每个 item 里 role 字段已经是 Role 枚举）
    member_list = []
    for item in items:
        member_list.append(
            MemberDetail(
                user_id=item["user_id"],
                role=item["role"],
                user=item["user"],
                joined_at=item["joined_at"],
                invited_by=item["invited_by"],
                is_current_user=item["is_current_user"],
            )
        )

    return ListMembersResponse(
        items=member_list,
        total=len(member_list),
    )


# ============================================================
# 端点 2：改角色
# ============================================================


@router.patch(
    "/tenants/{tenant_id}/members/{user_id}",
    response_model=ChangeRoleResponse,
    summary="Change a member's role (ADMIN+ only)",
)
async def change_role(
    tenant_id: UUID,
    user_id: UUID,
    payload: ChangeRoleRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    # ⚠️ 必须是 ADMIN 才能改
    actor_membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ChangeRoleResponse:
    """PATCH /api/v1/tenants/{tenant_id}/members/{user_id}

    修改某成员的角色。

    业务规则（service 层实现）：
    - 不能给 OWNER
    - 不能改自己
    - ADMIN 不能改 OWNER/ADMIN
    - 不能降级最后一个 OWNER
    """
    if tenant_id != actor_membership.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "tenant_mismatch", "message": "Wrong tenant"},
        )

    try:
        result = await membership_service.change_member_role(
            db,
            tenant_id=tenant_id,
            target_user_id=user_id,
            new_role=payload.role,
            actor_user_id=current_user.id,
            actor_role=actor_membership.role,
        )
    except MembershipError as exc:
        raise _membership_error_to_http(exc) from exc

    return ChangeRoleResponse(
        user_id=result["user_id"],
        old_role=result["old_role"],
        new_role=result["new_role"],
    )


# ============================================================
# 端点 3：踢人
# ============================================================


@router.delete(
    "/tenants/{tenant_id}/members/{user_id}",
    response_model=RemoveMemberResponse,
    summary="Remove a member from a tenant (ADMIN+ only)",
)
async def remove_member(
    tenant_id: UUID,
    user_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    actor_membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RemoveMemberResponse:
    """DELETE /api/v1/tenants/{tenant_id}/members/{user_id}

    从租户中移除某成员。

    业务规则（service 层）：
    - 不能踢自己
    - ADMIN 不能踢 OWNER/ADMIN
    - 不能踢最后一个 OWNER
    """
    if tenant_id != actor_membership.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "tenant_mismatch", "message": "Wrong tenant"},
        )

    try:
        result = await membership_service.remove_member(
            db,
            tenant_id=tenant_id,
            target_user_id=user_id,
            actor_user_id=current_user.id,
            actor_role=actor_membership.role,
        )
    except MembershipError as exc:
        raise _membership_error_to_http(exc) from exc

    return RemoveMemberResponse(
        removed_user_id=result["removed_user_id"],
        remaining_count=result["remaining_count"],
    )
