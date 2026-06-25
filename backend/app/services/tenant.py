"""Tenant 业务逻辑：列出我所在的租户、切换激活租户。

本文件专门处理"租户切换"相关操作，auth.py 处理用户登录注册。
两个 service 互相独立但共享同一套模型（User、Tenant、TenantMember）。

学习要点：
- Python 的 service 层 ≈ Java 的 @Service 注解类
- 区别：Python service 用"模块级函数"而不是 class，因为无状态
- 显式写注释告诉同事"这个函数的副作用是什么"
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import logger
from app.core.security import create_access_token, create_refresh_token
from app.models.membership import TenantMember
from app.models.tenant import Tenant
from app.models.user import User


class TenantError(Exception):
    """租户业务异常。端点层翻译成 4xx。

    用法：service 里校验失败 → raise TenantError(code, message) → 端点 catch → 返回 4xx

    为什么不用 ValueError 之类的标准异常：
    - 标准异常粒度太粗，错误码不够细
    - 自定义异常能让端点层"switch case"地处理不同业务错误
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# ============================================================
# 业务函数 1：列出当前用户加入的所有租户
# ============================================================


async def list_my_tenants(
    db: AsyncSession,
    user: User,
) -> list[dict[str, Any]]:
    """查询当前用户加入的所有租户，每个租户附带角色信息。

    Args:
        db: 异步数据库 session（由 FastAPI Depends 注入）
        user: 当前登录用户对象（已通过 get_current_user 验证）

    Returns:
        一个 list，每项是 dict：
        {
            "id": UUID,
            "name": str,
            "slug": str,
            "plan": str,
            "status": str,
            "role": Role,         # 当前用户在这个租户的角色
            "is_active": bool,    # 是否当前激活
            "created_at": datetime,
        }

    设计要点：
    - 用 selectinload 一次性把 memberships.tenant 都加载好，避免 N+1 查询
    - 这里我们没用外层 User.memberships，而是用直接 JOIN 查 TenantMember，
      性能更好（不需要把 User 的所有数据都拉出来）
    """
    # 第一步：查出 user 加入的所有 TenantMember（含租户信息和角色）
    stmt = (
        select(TenantMember)
        # selectinload(TenantMember.tenant) 会用一条 IN 查询把所有租户拉出来
        # 比 lazy load 快 N 倍，避免 N+1
        .options(selectinload(TenantMember.tenant))
        .where(TenantMember.user_id == user.id)
        # 按加入时间倒序：最近加入的排前面（前端 workspace 列表 UX 更好）
        .order_by(TenantMember.created_at.desc())
    )
    result = await db.execute(stmt)
    memberships = result.scalars().all()

    # 第二步：组装成前端要的结构
    # ⚠️ 关键：组装的过程必须在 session 还开着的时候做
    # 因为我们访问了 m.tenant.name、m.role 这些关系字段
    # 一旦 session close 之后访问，会抛 MissingGreenlet
    items: list[dict[str, Any]] = []
    for m in memberships:
        items.append(
            {
                "id": m.tenant.id,
                "name": m.tenant.name,
                "slug": m.tenant.slug,
                "plan": m.tenant.plan.value if hasattr(m.tenant.plan, "value") else m.tenant.plan,
                "status": m.tenant.status.value
                if hasattr(m.tenant.status, "value")
                else m.tenant.status,
                "role": m.role,
                "is_active": False,  # 调用方根据 token 里的 active_tenant_id 决定
                "created_at": m.tenant.created_at,
            }
        )

    return items


# ============================================================
# 业务函数 2：切换激活租户
# ============================================================


async def switch_active_tenant(
    db: AsyncSession,
    *,
    user: User,
    target_tenant_id: UUID,
) -> dict[str, Any]:
    """切换当前用户的激活租户，返回新的 token pair。

    Args:
        db: 异步数据库 session
        user: 当前登录用户
        target_tenant_id: 客户端请求要切换到的租户 ID

    Returns:
        {
            "access_token": str,    # 新的 access token，payload 里有新 active_tenant_id
            "refresh_token": str,   # 新的 refresh token（每次切换都重发，旧 token 失效）
            "expires_in": int,      # access token 剩余秒数
            "active_tenant": dict,  # 新激活租户的完整信息
        }

    Raises:
        TenantError:
            - "tenant_not_found": 租户不存在
            - "not_a_member": 当前用户不是这个租户的成员
            - "tenant_inactive": 租户被停用/暂停

    业务约束：
    1. 用户必须是目标租户的成员（OWNER/ADMIN/MEMBER/VIEWER 都行）
    2. 租户不能是 SUSPENDED/INACTIVE 状态
    3. 切换成功后，旧 access token 仍然有效直到过期（不强制失效）
       但前端调 /auth/me 会自动用新 token 重新拉数据
    """
    # 第一步：查目标租户存不存在
    target_tenant = await db.scalar(select(Tenant).where(Tenant.id == target_tenant_id))
    if target_tenant is None:
        raise TenantError("tenant_not_found", "Target tenant does not exist")

    # 第二步：校验租户状态
    # ⚠️ 关键：PG ENUM 在 SQLAlchemy 里的 .value 是小写（"active"），
    # 但 PG 库里存的是大写（"ACTIVE"）。我们用 .value 转成小写比最稳。
    target_status = (
        target_tenant.status.value
        if hasattr(target_tenant.status, "value")
        else str(target_tenant.status)
    )
    # 规范化：把可能的 "ACTIVE" / "Active" / "active" 统一成小写比
    target_status_normalized = target_status.lower()
    if target_status_normalized != "active":
        raise TenantError(
            "tenant_inactive",
            f"Tenant is {target_status_normalized}, cannot switch to it",
        )

    # 第三步：校验当前用户是不是这个租户的成员
    # 防止有人随便填一个 tenant_id 就把 token "切"过去
    membership = await db.scalar(
        select(TenantMember).where(
            TenantMember.user_id == user.id,
            TenantMember.tenant_id == target_tenant_id,
        )
    )
    if membership is None:
        raise TenantError("not_a_member", "You are not a member of this tenant")

    # 第四步：重新签发 token
    # 关键：active_tenant_id 要传新的那个！否则 token 里的 active_tenant_id 还是旧的
    new_access = create_access_token(
        user_id=user.id,
        active_tenant_id=target_tenant_id,
    )
    new_refresh = create_refresh_token(user.id)

    logger.info(
        "tenant.switched",
        user_id=str(user.id),
        from_tenant_id="?",  # 旧值从 token 来，service 不在这里解析
        to_tenant_id=str(target_tenant_id),
    )

    # 第五步：组装响应
    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "expires_in": settings.access_token_expire_minutes * 60,
        "active_tenant": {
            "id": target_tenant.id,
            "name": target_tenant.name,
            "slug": target_tenant.slug,
            "plan": target_tenant.plan.value
            if hasattr(target_tenant.plan, "value")
            else target_tenant.plan,
            "status": target_tenant.status.value
            if hasattr(target_tenant.status, "value")
            else target_tenant.status,
            "role": membership.role,
            "is_active": True,  # 切换之后这个就是 active 的了
            "created_at": target_tenant.created_at,
        },
    }


# ============================================================
# 业务函数 3：拿"用户默认激活的租户"（用于登录/注册时定初始 active tenant）
# ============================================================


async def get_default_tenant_for_user(
    db: AsyncSession,
    user_id: UUID,
) -> TenantMember | None:
    """拿到用户应该默认激活的租户。

    选择策略（按优先级降序）：
    1. 用户是 OWNER 的租户（说明是他自己创建的，活跃度最高）
    2. 按加入时间倒序的最近一个
    3. 都没有就返回 None（用户还没加入任何租户）

    Returns:
        TenantMember 对象（含 tenant 关系），或者 None
    """
    stmt = (
        select(TenantMember)
        .options(selectinload(TenantMember.tenant))
        .where(TenantMember.user_id == user_id)
        # 优先 OWNER，然后按时间倒序
        .order_by(
            # 关键：PG ENUM 是按定义顺序存储的，可以用 CASE WHEN 排序
            # 但更简单的做法是先查所有再在 Python 里排序（数据量小）
            TenantMember.created_at.desc(),
        )
    )
    result = await db.execute(stmt)
    memberships = list(result.scalars().all())

    if not memberships:
        return None

    # 优先 OWNER
    owner_memberships = [m for m in memberships if m.role.value == "OWNER"]
    if owner_memberships:
        return owner_memberships[0]

    # 退而求其次：最近加入的
    return memberships[0]
