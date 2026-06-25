"""Membership 管理业务逻辑：列成员、改角色、踢人。

学习要点（给 Java 背景的同事）：
- 这是"成员管理"的核心 service
- 跟 services/invitation.py 类似，但是针对"已经是成员"的用户
- 业务约束很多（OWNER 保护、不能改自己、不能降级最后一个 OWNER），
  全在这里实现
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.membership import Role, TenantMember


class MembershipError(Exception):
    """成员管理业务异常。端点层翻译成 4xx。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# 角色等级表（跟 deps.py 里 _ROLE_HIERARCHY 一致）
# ⚠️ 这里不依赖 deps.py 避免循环 import
_ROLE_HIERARCHY: dict[Role, int] = {
    Role.OWNER: 4,
    Role.ADMIN: 3,
    Role.MEMBER: 2,
    Role.VIEWER: 1,
}


# ============================================================
# 业务函数 1：列某租户的所有成员
# ============================================================


async def list_members(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    current_user_id: UUID,
) -> list[dict[str, Any]]:
    """列出某租户的全部成员。

    Args:
        db: 异步 session
        tenant_id: 当前激活租户
        current_user_id: 当前登录用户（用来标 is_current_user）

    Returns:
        成员列表，按 role 倒序 + joined_at 升序

    排序策略：
    - OWNER 排最前（方便看谁是老板）
    - 同 role 内按加入时间升序（老成员在前）
    """
    # selectinload 一次拉完 user 关系
    # 注意：TenantMember 用的是 TimestampMixin 的 created_at（不是 joined_at）
    result = await db.execute(
        select(TenantMember)
        .options(selectinload(TenantMember.user))
        .where(TenantMember.tenant_id == tenant_id)
        .order_by(TenantMember.created_at.asc())
    )
    members = list(result.scalars().all())

    # ⚠️ 必须在 session 还开着时构造 dict
    items: list[dict[str, Any]] = []
    for m in members:
        items.append(
            {
                "user_id": m.user_id,
                "role": m.role,
                "user": {
                    "id": m.user.id,
                    "email": m.user.email,
                    "full_name": m.user.full_name,
                    "status": m.user.status.value
                    if hasattr(m.user.status, "value")
                    else m.user.status,
                },
                "joined_at": m.created_at,  # 用 created_at 表示加入时间
                "invited_by": m.invited_by,
                "is_current_user": m.user_id == current_user_id,
            }
        )

    # 按 role 等级倒序排序（OWNER 在前）
    items.sort(key=lambda m: -_ROLE_HIERARCHY[m["role"]])

    return items


# ============================================================
# 业务函数 2：改成员角色
# ============================================================


async def change_member_role(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    target_user_id: UUID,
    new_role: Role,
    actor_user_id: UUID,
    actor_role: Role,
) -> dict[str, Any]:
    """修改某成员的角色。

    Args:
        db: 异步 session
        tenant_id: 当前激活租户
        target_user_id: 被改的人
        new_role: 新角色
        actor_user_id: 操作用户（你）
        actor_role: 你的当前角色

    Returns:
        { user_id, old_role, new_role, message }

    Raises:
        MembershipError:
            - "cannot_assign_owner": 不允许通过改角色给 OWNER
            - "member_not_found": 目标不是该租户成员
            - "self_role_change": 不能改自己的角色
            - "permission_denied": 你的角色不够（MEMBER 想改 ADMIN 的权限）
            - "downgrade_last_owner": 不能降级最后一个 OWNER

    ⚠️ 业务规则（必须严格遵守）：
    1. 不能给 OWNER（绕过安全模型）
    2. 不能改自己的角色（防止 ADMIN 把自己降级到 VIEWER 后破坏审计）
    3. ADMIN 不能改 OWNER 的角色（防止权限扩张）
    4. MEMBER/VIEWER 根本不能调这个端点（已在端点层 require_role(ADMIN) 拦）
    5. 不能降级最后一个 OWNER（防止租户变成"无主之地"）
    """
    # ---------- 规则 1：不能给 OWNER ----------
    if new_role == Role.OWNER:
        raise MembershipError(
            "cannot_assign_owner",
            "OWNER role cannot be assigned via role change",
        )

    # ---------- 规则 2：不能改自己 ----------
    if target_user_id == actor_user_id:
        raise MembershipError(
            "self_role_change",
            "Cannot change your own role (ask another admin)",
        )

    # ---------- 规则 3：权限检查 ----------
    # 你是 ADMIN 的话：能改 MEMBER/VIEWER，但不能改 OWNER/ADMIN
    # 你是 OWNER 的话：能改任何人
    target_member = await db.scalar(
        select(TenantMember)
        .options(selectinload(TenantMember.user))
        .where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == target_user_id,
        )
    )
    if target_member is None:
        raise MembershipError(
            "member_not_found",
            "Target user is not a member of this tenant",
        )

    if (
        actor_role == Role.ADMIN
        and _ROLE_HIERARCHY[target_member.role] >= _ROLE_HIERARCHY[Role.ADMIN]
    ):
        # ADMIN 只能动比自己等级低的人
        raise MembershipError(
            "permission_denied",
            "Admins cannot change roles of owners or other admins",
        )
    # OWNER 没限制（但规则 2 已经拦住改自己）
    # Role.MEMBER/VIEWER 调不到这个端点（已被 require_role 拦）

    # ---------- 规则 4：不能降级最后一个 OWNER ----------
    if target_member.role == Role.OWNER and new_role != Role.OWNER:
        # 数这个租户里还有多少 OWNER
        from sqlalchemy import func

        result = await db.execute(
            select(func.count())
            .select_from(TenantMember)
            .where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.role == Role.OWNER,
            )
        )
        total_owners = result.scalar() or 0
        if total_owners <= 1:
            raise MembershipError(
                "downgrade_last_owner",
                "Cannot downgrade the last owner of the tenant",
            )

    # ---------- 校验通过，执行修改 ----------
    old_role = target_member.role
    target_member.role = new_role
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise MembershipError("update_failed", "Failed to update role") from exc

    # 重新查一次拿最新状态
    await db.refresh(target_member)

    logger.info(
        "membership.role_changed",
        tenant_id=str(tenant_id),
        target_user_id=str(target_user_id),
        old_role=old_role.value,
        new_role=new_role.value,
        actor_user_id=str(actor_user_id),
    )

    return {
        "user_id": target_user_id,
        "old_role": old_role,
        "new_role": new_role,
    }


# ============================================================
# 业务函数 3：踢人
# ============================================================


async def remove_member(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    target_user_id: UUID,
    actor_user_id: UUID,
    actor_role: Role,
) -> dict[str, Any]:
    """从租户中移除某成员。

    Args:
        db: 异步 session
        tenant_id: 当前激活租户
        target_user_id: 被踢的人
        actor_user_id: 操作用户
        actor_role: 操作用户的角色

    Returns:
        { removed_user_id, remaining_count }

    Raises:
        MembershipError:
            - "member_not_found": 目标不是成员
            - "self_remove": 不能踢自己
            - "permission_denied": 权限不够
            - "remove_last_owner": 不能踢最后一个 OWNER

    ⚠️ 业务规则（改角色 + 踢人 共用大部分逻辑）：
    1. 不能踢自己
    2. ADMIN 不能踢 OWNER/ADMIN
    3. 不能踢最后一个 OWNER
    4. OWNER 可以踢任何人（除了自己）
    """
    # ---------- 规则 1：不能踢自己 ----------
    if target_user_id == actor_user_id:
        raise MembershipError(
            "self_remove",
            "Cannot remove yourself (ask another admin to remove you)",
        )

    # ---------- 找目标成员 ----------
    target_member = await db.scalar(
        select(TenantMember).where(
            TenantMember.tenant_id == tenant_id,
            TenantMember.user_id == target_user_id,
        )
    )
    if target_member is None:
        raise MembershipError(
            "member_not_found",
            "Target user is not a member of this tenant",
        )

    # ---------- 规则 2：权限检查 ----------
    if (
        actor_role == Role.ADMIN
        and _ROLE_HIERARCHY[target_member.role] >= _ROLE_HIERARCHY[Role.ADMIN]
    ):
        raise MembershipError(
            "permission_denied",
            "Admins cannot remove owners or other admins",
        )
    # OWNER 仍然受规则 1 限制

    # ---------- 规则 3：不能踢最后一个 OWNER ----------
    if target_member.role == Role.OWNER:
        from sqlalchemy import func

        result = await db.execute(
            select(func.count())
            .select_from(TenantMember)
            .where(
                TenantMember.tenant_id == tenant_id,
                TenantMember.role == Role.OWNER,
            )
        )
        total_owners = result.scalar() or 0
        if total_owners <= 1:
            raise MembershipError(
                "remove_last_owner",
                "Cannot remove the last owner of the tenant",
            )

    # ---------- 执行踢人 ----------
    await db.delete(target_member)
    await db.commit()

    # 数剩余成员
    from sqlalchemy import func

    result = await db.execute(
        select(func.count()).select_from(TenantMember).where(TenantMember.tenant_id == tenant_id)
    )
    remaining = result.scalar() or 0

    logger.info(
        "membership.removed",
        tenant_id=str(tenant_id),
        target_user_id=str(target_user_id),
        actor_user_id=str(actor_user_id),
        remaining=remaining,
    )

    return {
        "removed_user_id": target_user_id,
        "remaining_count": remaining,
    }
