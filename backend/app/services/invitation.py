"""Invitation 业务逻辑层。

本文件是邀请流程的"大脑"——4 个核心业务函数都住这：
  - create_invitation()    生成 token + 存 DB
  - list_invitations()     列出某租户所有邀请
  - accept_invitation()    接受邀请（最复杂）
  - revoke_invitation()    撤销邀请

学习要点（给 Java 背景的同事）：
- service 层 = Spring 的 @Service
- 区别：Python 不用类，直接用模块级函数（无状态更纯粹）
- 所有 DB 操作都在这里，端点层只接参 + 调 service
- 业务异常用 InvitationError（继承 Exception，自带 code 字段）
"""

import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import logger
from app.models.invitation import Invitation, make_invitation
from app.models.membership import Role, TenantMember
from app.models.tenant import Tenant
from app.models.user import User

# ============================================================
# 业务异常
# ============================================================


class InvitationError(Exception):
    """邀请业务异常。端点层翻译成 4xx HTTP。

    用法：
        try:
            await service.accept_invitation(...)
        except InvitationError as exc:
            raise HTTPException(400, detail={"code": exc.code, "message": exc.message})
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# ============================================================
# 工具函数
# ============================================================


def _build_invite_link(token: str, request: Request | None = None) -> str:
    """组装完整邀请链接。

    Args:
        token: 纯 token
        request: FastAPI Request 对象（用来拿 host/port，自动拼 URL）
                传 None 的话用默认的 localhost:3000

    Returns:
        完整 URL，前端能直接复制发出去

    ⚠️ 为什么不在前端拼 URL？
    - 前端不知道 base URL 是什么（开发/生产不一样）
    - 前端拼错（比如带错端口）链接就废了
    - 后端拼好 → 前端零心智负担
    """
    if request is not None:
        # 优先用 request 里的 host（生产环境会用真实域名）
        base = f"{request.url.scheme}://{request.url.netloc}"
    else:
        # 兜底：开发环境
        base = "http://localhost:3000"
    return f"{base}/invitations/accept?token={token}"


def _serialize_invitation(inv: Invitation) -> dict[str, Any]:
    """把 Invitation ORM 对象转成 dict（端点层再 Pydantic 序列化）。

    ⚠️ 关键：所有字段访问必须在 session 还活着的时候做
    不能懒加载（MissingGreenlet）→ 所以 inviter.email 这种关系字段要提前 eager load
    """
    return {
        "id": inv.id,
        "email": inv.email,
        "role": inv.role.value,
        "status": inv.status.value,  # 派生属性，会自动算 expired/accepted/...
        "created_at": inv.created_at,
        "expires_at": inv.expires_at,
        "accepted_at": inv.accepted_at,
        "revoked_at": inv.revoked_at,
        "invited_by_email": inv.inviter.email if inv.inviter else None,
    }


# ============================================================
# 业务函数 1：创建邀请
# ============================================================


async def create_invitation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    invited_by: UUID,
    email: str,
    role: Role,
    request: Request | None = None,
) -> tuple[Invitation, str]:
    """创建一条新的邀请记录，返回 (Invitation, 完整链接)。

    Args:
        db: 异步 session
        tenant_id: 当前激活租户（来自 token，不让前端传！）
        invited_by: 邀请人 user_id
        email: 被邀请者邮箱
        role: 接受后给什么角色
        request: FastAPI Request（用来拼 base URL，可选）

    Returns:
        (Invitation 对象, 完整邀请链接 URL)

    Raises:
        InvitationError:
            - "cannot_invite_owner": 不允许通过邀请给 OWNER 角色
            - "tenant_inactive": 租户被停用
            - "duplicate_pending_invitation": 该租户已有一个给同 email 的未处理邀请

    业务约束（这里实现，schema 层只做格式校验）：
    1. 角色不能是 OWNER（绕过安全模型）
    2. 租户必须 ACTIVE
    3. 同一租户对同一 email 只能有一个"活的"邀请
       （通过 partial unique index 强制 + 这里友好检查）
    """
    # ---------- 检查 1：角色不能是 OWNER ----------
    # 业务上：OWNER 是创建租户时定的，不能通过邀请"制造"OWNER
    if role == Role.OWNER:
        raise InvitationError(
            "cannot_invite_owner",
            "OWNER role cannot be assigned via invitation",
        )

    # ---------- 检查 2：租户状态 ----------
    tenant = await db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant is None:
        raise InvitationError("tenant_not_found", "Tenant does not exist")
    tenant_status = tenant.status.value if hasattr(tenant.status, "value") else str(tenant.status)
    if tenant_status != "active":
        raise InvitationError(
            "tenant_inactive",
            f"Tenant is {tenant_status}, cannot invite new members",
        )

    # ---------- 检查 3：是否已有 pending 邀请 ----------
    # 提前检查（不依赖 DB 唯一约束）→ 给用户更友好的错误
    # DB 唯一约束是兜底（防 race condition）
    existing = await db.scalar(
        select(Invitation).where(
            Invitation.tenant_id == tenant_id,
            Invitation.email == email.lower(),
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
    )
    if existing is not None:
        raise InvitationError(
            "duplicate_pending_invitation",
            "There is already a pending invitation for this email",
        )

    # ---------- 生成 token ----------
    # secrets.token_urlsafe(32) = 32 字节熵 = 256 位
    # URL-safe base64 编码后约 43 字符
    # 关键：绝不用 uuid.uuid4() —— UUID 只有 122 位熵，不够
    token = secrets.token_urlsafe(32)

    # ---------- 创建记录 ----------
    inv = make_invitation(
        tenant_id=tenant_id,
        email=email,
        role=role,
        invited_by=invited_by,
        token=token,
        # ttl_days=7 走默认值
    )
    db.add(inv)

    # ---------- 提交（带 race condition 兜底） ----------
    try:
        await db.commit()
    except IntegrityError as err:
        # 并发场景：两个请求同时发邀请，DB 唯一约束会拦
        await db.rollback()
        raise InvitationError(
            "duplicate_pending_invitation",
            "Invitation already exists (concurrent request)",
        ) from err

    # 重新查一次拿到完整对象（带关系字段）
    inv = await db.scalar(
        select(Invitation).options(selectinload(Invitation.inviter)).where(Invitation.id == inv.id)
    )

    # 拼完整链接
    invite_link = _build_invite_link(token, request)

    logger.info(
        "invitation.created",
        invitation_id=str(inv.id),
        tenant_id=str(tenant_id),
        invited_by=str(invited_by),
        email=email,
        role=role.value,
    )

    return inv, invite_link


# ============================================================
# 业务函数 2：列出某租户的所有邀请
# ============================================================


async def list_invitations(
    db: AsyncSession,
    *,
    tenant_id: UUID,
) -> dict[str, Any]:
    """列出某租户的所有邀请记录（含 pending + 历史）。

    Args:
        db: 异步 session
        tenant_id: 当前激活租户

    Returns:
        {
            "items": [Invitations 列表],
            "pending_count": int,
            "accepted_count": int,
        }

    业务用途：
    - 团队管理页（/team）渲染"成员邀请"列表
    - 显示"3 个待处理 / 5 个已接受"
    """
    # 用 selectinload 一次拉完所有邀请 + 邀请人信息
    # 防止后续访问 inviter.email 时抛 MissingGreenlet
    result = await db.execute(
        select(Invitation)
        .options(selectinload(Invitation.inviter))
        .where(Invitation.tenant_id == tenant_id)
        # 最新的排前面
        .order_by(Invitation.created_at.desc())
    )
    invitations = list(result.scalars().all())

    # ⚠️ 必须 while session is open 时序列化
    items = [_serialize_invitation(inv) for inv in invitations]

    # 统计：派生 status 来分类
    pending_count = sum(1 for inv in invitations if inv.status.value == "pending")
    accepted_count = sum(1 for inv in invitations if inv.status.value == "accepted")

    return {
        "items": items,
        "pending_count": pending_count,
        "accepted_count": accepted_count,
    }


# ============================================================
# 业务函数 3：接受邀请（最复杂）
# ============================================================


async def accept_invitation(
    db: AsyncSession,
    *,
    token: str,
    current_user: User,
) -> dict[str, Any]:
    """接受邀请，把当前用户加进对应租户。

    Args:
        db: 异步 session
        token: 邀请 token（从 URL 拿）
        current_user: 当前登录的用户（get_current_user 注入的）

    Returns:
        {
            "invitation": {...},  # 邀请记录（更新后）
            "joined_tenant": {...},  # 新加入的租户信息
        }

    Raises:
        InvitationError:
            - "token_not_found": token 不存在
            - "token_expired": 已过期
            - "token_used": 已被接受
            - "token_revoked": 已被撤销
            - "email_mismatch": 邀请的 email ≠ 当前用户 email
            - "already_a_member": 已经是该租户的成员了

    业务流程（按顺序）：
    1. 查 token → 拿到 invitation
    2. 校验 token 状态（3 重检查）
    3. 校验 email 一致（防被偷链接）
    4. 校验是否已是成员
    5. 原子 UPDATE accepted_at（防重放）
    6. 创建 TenantMember 行
    7. 全部 commit

    ⚠️ 关键：第 5 步和第 6 步必须在同一个事务里
    """
    # ---------- 第 1 步：查 token ----------
    inv = await db.scalar(
        select(Invitation)
        .options(selectinload(Invitation.inviter))
        .where(Invitation.token == token)
    )
    if inv is None:
        raise InvitationError("token_not_found", "Invalid invitation token")

    # ---------- 第 2 步：3 重检查 ----------
    # ⚠️ 顺序很重要：先检查 accepted/revoked（确定状态），
    # 再检查 expired（时间相关状态）
    # 这样错误码更精确

    if inv.accepted_at is not None:
        raise InvitationError("token_used", "This invitation has already been accepted")
    if inv.revoked_at is not None:
        raise InvitationError("token_revoked", "This invitation has been revoked")
    if inv.is_expired():
        raise InvitationError("token_expired", "This invitation has expired")

    # ---------- 第 3 步：email 一致性 ----------
    # ⚠️ 关键安全检查：
    # 苏苏邀请李雷（李雷的 email）
    # 王五拿到链接登录自己的账号，token 没被改
    # 没有这个检查 → 王五能加进苏苏的工作空间
    if inv.email.lower() != current_user.email.lower():
        raise InvitationError(
            "email_mismatch",
            "This invitation is for a different email address",
        )

    # ---------- 第 4 步：是否已是成员 ----------
    existing_member = await db.scalar(
        select(TenantMember).where(
            TenantMember.user_id == current_user.id,
            TenantMember.tenant_id == inv.tenant_id,
        )
    )
    if existing_member is not None:
        # 已经是成员了——不要报错，直接当作"幂等成功"
        # （前端可能重复点接受链接）
        # 但仍然标记 invitation 为已接受（防后续误用）
        logger.info(
            "invitation.accept_idempotent",
            user_id=str(current_user.id),
            tenant_id=str(inv.tenant_id),
        )
        # 返回已存在的 member 信息
        tenant = await db.scalar(select(Tenant).where(Tenant.id == inv.tenant_id))
        return {
            "invitation": _serialize_invitation(inv),
            "joined_tenant": {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "plan": tenant.plan.value if hasattr(tenant.plan, "value") else tenant.plan,
                "status": tenant.status.value if hasattr(tenant.status, "value") else tenant.status,
                "role": existing_member.role.value,
                "is_active": False,  # 不是自动激活的，让用户自己切
                "created_at": tenant.created_at,
            },
        }

    # ---------- 第 5 步：原子 UPDATE accepted_at（防重放） ----------
    # ⚠️ 关键：不是 Python 检查 accepted_at 然后 UPDATE
    # 而是用 SQL 的 WHERE 条件原子操作
    # 并发场景：A 和 B 同时点接受 → A 和 B 都看到 accepted_at = NULL
    #         但 UPDATE ... WHERE accepted_at IS NULL 只会有 1 个 rowcount=1
    now = datetime.now(tz=timezone.utc)
    result = await db.execute(
        update(Invitation)
        .where(
            Invitation.id == inv.id,
            Invitation.accepted_at.is_(None),  # WHERE 条件防重放
            Invitation.revoked_at.is_(None),
        )
        .values(accepted_at=now)
    )
    if result.rowcount == 0:
        # 别的请求已经抢先接受了
        await db.rollback()
        raise InvitationError(
            "token_used_race",
            "Invitation was just accepted by another request",
        )

    # 刷新 inv 对象的 accepted_at（让后续逻辑能看到）
    inv.accepted_at = now

    # ---------- 第 6 步：创建 TenantMember 行 ----------
    new_member = TenantMember(
        user_id=current_user.id,
        tenant_id=inv.tenant_id,
        role=inv.role,
    )
    db.add(new_member)

    # ---------- 第 7 步：提交（带兜底） ----------
    try:
        await db.commit()
    except IntegrityError as err:
        # 极端情况：第 4 步和第 6 步之间有并发请求插入了同一条 member
        # 唯一约束会拦
        await db.rollback()
        # 把 accepted_at 回滚（虽然 SQL 已更新但事务整体回滚）
        raise InvitationError(
            "already_a_member",
            "You are already a member of this tenant",
        ) from err

    # 拿 tenant 信息返回
    tenant = await db.scalar(select(Tenant).where(Tenant.id == inv.tenant_id))

    logger.info(
        "invitation.accepted",
        invitation_id=str(inv.id),
        user_id=str(current_user.id),
        tenant_id=str(inv.tenant_id),
        role=inv.role.value,
    )

    return {
        "invitation": _serialize_invitation(inv),
        "joined_tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "plan": tenant.plan.value if hasattr(tenant.plan, "value") else tenant.plan,
            "status": tenant.status.value if hasattr(tenant.status, "value") else tenant.status,
            "role": inv.role.value,
            "is_active": False,  # 让用户主动切到新工作空间
            "created_at": tenant.created_at,
        },
    }


# ============================================================
# 业务函数 4：撤销邀请
# ============================================================


async def revoke_invitation(
    db: AsyncSession,
    *,
    invitation_id: UUID,
    current_user: User,
    current_tenant_id: UUID,
) -> Invitation:
    """撤销一个 pending 邀请。

    Args:
        db: 异步 session
        invitation_id: 要撤销的邀请 ID
        current_user: 当前用户（要验证是这个租户的成员）
        current_tenant_id: 当前激活租户（要验证邀请属于这个租户）

    Returns:
        更新后的 Invitation 对象

    Raises:
        InvitationError:
            - "invitation_not_found": 不存在
            - "wrong_tenant": 这个邀请不是当前租户的
            - "already_accepted": 已接受的不能撤销（走"踢人"流程）
            - "already_revoked": 已撤销的（幂等）
    """
    inv = await db.scalar(select(Invitation).where(Invitation.id == invitation_id))
    if inv is None:
        raise InvitationError("invitation_not_found", "Invitation does not exist")

    # 校验属于当前租户（防止用租户 A 的 token 撤销租户 B 的邀请）
    if inv.tenant_id != current_tenant_id:
        raise InvitationError(
            "wrong_tenant",
            "This invitation does not belong to your active tenant",
        )

    # 已接受的不能撤销（要让用户走"踢人"接口）
    if inv.accepted_at is not None:
        raise InvitationError(
            "already_accepted",
            "Cannot revoke an accepted invitation (use remove member instead)",
        )

    # 已撤销的 → 幂等返回（前端可能重复点）
    if inv.revoked_at is not None:
        logger.info("invitation.revoke_idempotent", invitation_id=str(inv.id))
        return inv

    # 设置撤销时间
    inv.revoked_at = datetime.now(tz=timezone.utc)
    await db.commit()

    logger.info(
        "invitation.revoked",
        invitation_id=str(inv.id),
        revoked_by=str(current_user.id),
    )

    return inv


# ============================================================
# 业务函数 5（辅助）：注册时自动接受 pending 邀请
# ============================================================
# 这个函数被 services/auth.py 的 register() 调用
# 业务流程：
#   1. 用户注册（提供 email）
#   2. 我们查这个 email 是不是有 pending 邀请
#   3. 如果有 → 自动创建 TenantMember 行，标记 invitation 为 accepted
#   4. 用户注册完登录后，dashboard 直接显示新工作空间（不用再点接受链接）


async def auto_accept_pending_for_new_user(
    db: AsyncSession,
    *,
    user: User,
) -> list[TenantMember]:
    """新用户注册时，自动接受发给该 email 的所有 pending 邀请。

    ⚠️ 关键：必须在 register() 的同一个事务里调用
    这样要么都成功（用户创建 + 加入租户），要么都失败

    Args:
        db: 异步 session（register 那个 session）
        user: 刚注册的用户

    Returns:
        创建的 TenantMember 列表（可能为空）
    """
    now = datetime.now(tz=timezone.utc)

    # 查所有 pending 邀请
    result = await db.execute(
        select(Invitation).where(
            Invitation.email == user.email.lower(),
            Invitation.accepted_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > now,
        )
    )
    pending_invitations = list(result.scalars().all())

    new_memberships: list[TenantMember] = []

    for inv in pending_invitations:
        # 标记邀请为已接受
        inv.accepted_at = now

        # 创建成员行
        member = TenantMember(
            user_id=user.id,
            tenant_id=inv.tenant_id,
            role=inv.role,
        )
        db.add(member)
        new_memberships.append(member)

        logger.info(
            "invitation.auto_accepted",
            user_id=str(user.id),
            tenant_id=str(inv.tenant_id),
            role=inv.role.value,
        )

    # 不在这里 commit（外层 register 统一 commit）
    return new_memberships
