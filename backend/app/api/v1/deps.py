"""API dependencies for FastAPI endpoints.

本文件是"端点层"和"底层服务"之间的胶水。

学习要点（给 Java 背景的同事）：
- Python 的"依赖注入" = Spring 的 @Autowired，但用 Depends() 函数式表达
- Annotated[类型, Depends(函数)] 是 FastAPI 推荐写法，IDE 提示更准
- 工厂函数（return checker）用来"带参数的依赖"——这是重点

文件结构：
1. _bearer              解析 Authorization 头的工具
2. get_current_user     从 token 拿当前 User 对象（身份认证）
3. _ROLE_HIERARCHY      角色等级表（OWNER > ADMIN > MEMBER > VIEWER）
4. get_active_tenant_id 从 token 拿 active_tenant_id（辅助）
5. require_role(...)    工厂函数：要求"最低角色"的成员才能进（权限检查）
6. get_active_membership 便捷函数：拿当前 membership 对象
"""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.membership import Role, TenantMember
from app.models.user import User

# ============================================================
# 1. _bearer：Authorization 头解析器
# ============================================================
# auto_error=False：拿不到 token 时返回 None 而不是自动抛 401
# 这样我们可以在 get_current_user 里统一抛 401，错误格式可控
_bearer = HTTPBearer(auto_error=False, description="JWT access token")


# ============================================================
# 2. get_current_user：从 Bearer token 拿当前用户
# ============================================================
# 这是"身份认证"层（Authentication）
# 任何需要登录的端点都要 Depends 这个


async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """解析 Authorization 头，返回当前登录的 User 对象。

    失败场景（全部返回 401）：
    - 没传 Authorization 头
    - 格式不是 "Bearer xxx"
    - token 签名错 / 过期 / 类型错
    - token 里的 user_id 在 DB 里查不到（用户被删了）

    Returns:
        User 对象（带所有字段，包括 hashed_password，但**不要**返回给前端）

    ⚠️ 安全提示：返回的 User 对象**包含** hashed_password。
    业务端点拿到 User 后，要么只取自己需要的字段，要么用 UserPublic schema 序列化。
    绝对不能把 User 对象原样塞进响应。
    """
    if creds is None or creds.scheme.lower() != "bearer" or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(creds.credentials, expected_type="access")
        user_id = UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )
    return user


# ============================================================
# 3. _ROLE_HIERARCHY：角色等级表
# ============================================================
# 用来判断"当前角色 ≥ 最低要求角色"吗
# 比如 require_role(Role.MEMBER)：OWNER/ADMIN/MEMBER 都通过，VIEWER 不通过
#
# 为什么是"等级"而不是"集合"？
# - "集合"写法：require_role([Role.MEMBER, Role.ADMIN, Role.OWNER]) 要写 3 个
# - "等级"写法：require_role(Role.MEMBER) 写 1 个，未来加角色不用改代码

_ROLE_HIERARCHY: dict[Role, int] = {
    Role.OWNER: 4,  # 最高，所有权限
    Role.ADMIN: 3,  # 团队管理，但不能删租户/转让
    Role.MEMBER: 2,  # 日常干活（上传/写/AI）
    Role.VIEWER: 1,  # 只读
}


def _role_at_least(actual: Role, required: Role) -> bool:
    """判断 actual 角色是否 ≥ required 角色。

    例：
    - _role_at_least(Role.OWNER, Role.MEMBER) → True（OWNER ≥ MEMBER）
    - _role_at_least(Role.VIEWER, Role.MEMBER) → False（VIEWER < MEMBER）
    """
    return _ROLE_HIERARCHY[actual] >= _ROLE_HIERARCHY[required]


# ============================================================
# 4. get_active_tenant_id：从 token 拿当前激活租户
# ============================================================
# 这是个"辅助"依赖，专门给 require_role 用
# 因为权限检查需要知道"在哪个租户"，所以这个值要先去 token 里解
#
# ⚠️ 关键：这里的 active_tenant_id **不能**完全信任
# 它只是"用户上次切换时记的"，可能是过期的（用户被踢了、租户被停了）
# 所以 require_role 拿到这个值后，要**重新查 DB 验证**


async def get_active_tenant_id(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> UUID | None:
    """从 access token 的 payload 里拿 active_tenant_id。

    Returns:
        UUID 或 None（token 里没有这个字段，比如注册后还没切过租户）

    ⚠️ 这个值**不能用于业务判断**，只能作为"期望的目标租户"。
    业务接口拿到后必须用 require_role 再校验一次。
    """
    if creds is None or not creds.credentials:
        return None
    try:
        payload = decode_token(creds.credentials, expected_type="access")
    except ValueError:
        return None
    tid = payload.get("active_tenant_id")
    return UUID(tid) if tid else None


# ============================================================
# 5. require_role(...)：核心：要求最低角色的工厂函数
# ============================================================
# ⚠️ 为什么是"工厂函数"而不是普通 Depends？
# 因为我们要在**调用时传参数**（要求什么角色）。
# 普通依赖 get_current_user() 没参数，可以直接当 Depends 用。
# 但 require_role(Role.ADMIN) 带了参数，必须先调用 require_role 一次，
# 它的返回值才是真正的依赖函数。
#
# 写法：
#   Depends(require_role(Role.ADMIN))
#   ^^^^^^^^   ^^^^^^^^^^^^^^^^^^^^^^^^
#   FastAPI 标记  工厂调用：返回内层 checker 函数
#
# 等价 Java 写法：
#   @PreAuthorize("hasRole('ADMIN')")  ← Spring Security
#   我们的写法：Depends(require_role(Role.ADMIN))


def require_role(min_role: Role):
    """工厂函数：返回一个 FastAPI 依赖，要求当前用户是"某租户的成员且角色≥min_role"。

    Args:
        min_role: 最低要求的角色。例：Role.MEMBER 表示 OWNER/ADMIN/MEMBER 都能进

    Returns:
        一个 async 函数（FastAPI 依赖），调用它会执行检查并返回 TenantMember

    Raises (FastAPI 自动捕获并转 4xx):
        401: 没登录 / token 无效（继承自 get_current_user）
        400: token 里没有 active_tenant_id（用户还没选工作空间）
        403: 当前用户不是该租户的成员 / 角色不够

    用法：
        @router.post("/documents/upload")
        async def upload_doc(
            user: User = Depends(get_current_user),
            membership: TenantMember = Depends(require_role(Role.MEMBER)),
        ):
            # 进到这里说明：
            # 1. user 已登录
            # 2. user 在 token 写的 active_tenant_id 是 MEMBER 及以上
            ...
    """

    # 闭包：内层 checker 函数能"看到"外层的 min_role
    async def checker(
        # get_current_user 自动跑：失败 → 401
        user: Annotated[User, Depends(get_current_user)],
        # get_active_tenant_id 自动跑：失败 → 返回 None
        tenant_id: Annotated[UUID | None, Depends(get_active_tenant_id)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> TenantMember:
        # ---------- 检查 1：必须有激活的租户 ----------
        if tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "no_active_tenant",
                    "message": "No active tenant. Please switch to one first.",
                },
            )

        # ---------- 检查 2：必须是该租户的成员 ----------
        # ⚠️ 关键：不能用 token 里的 active_tenant_id 直接信
        # 必须查 DB 确认 membership 还在
        # 原因：用户可能已被踢出该租户（token 还没过期）
        membership = await db.scalar(
            select(TenantMember).where(
                TenantMember.user_id == user.id,
                TenantMember.tenant_id == tenant_id,
            )
        )
        if membership is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "not_a_member",
                    "message": "You are not a member of this tenant",
                },
            )

        # ---------- 检查 3：角色等级 ----------
        # 例：min_role=MEMBER → OWNER/ADMIN/MEMBER 通过，VIEWER 拒绝
        if not _role_at_least(membership.role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "insufficient_role",
                    "message": (
                        f"This action requires at least {min_role.value} role, "
                        f"but you are {membership.role.value}"
                    ),
                },
            )

        return membership

    # 关键：返回内层函数。FastAPI 看到 Depends(callable) 会自动 await 它
    return checker


# ============================================================
# 6. get_active_membership：便捷函数，拿当前 membership
# ============================================================
# 有些业务接口**只关心**"我在这个租户是不是成员"，不要求特定角色
# 这种场景下用 require_role(Role.VIEWER) 等价于"任何成员"
# 但更清晰的写法是直接暴露这个便捷函数
#
# 用法：
#   membership: TenantMember = Depends(get_active_membership)
# 等价于：
#   membership: TenantMember = Depends(require_role(Role.VIEWER))


async def get_active_membership(
    user: Annotated[User, Depends(get_current_user)],
    tenant_id: Annotated[UUID | None, Depends(get_active_tenant_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantMember:
    """拿当前用户在当前激活租户的成员关系（不检查角色等级）。

    用法举例：GET /tenants/{id}/settings 这种"看设置"的接口，
    VIEWER 也能调（看得到），但不能改（用 require_role(ADMIN)）。

    Returns:
        TenantMember 对象（含 tenant 关系，可直接 .tenant.name）

    Raises:
        400: 没有 active tenant
        403: 不是成员
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "no_active_tenant", "message": "No active tenant"},
        )

    # selectinload 让 m.tenant.name 不抛 MissingGreenlet
    from sqlalchemy.orm import selectinload  # 局部 import 避免循环

    membership = await db.scalar(
        select(TenantMember)
        .options(selectinload(TenantMember.tenant))
        .where(
            TenantMember.user_id == user.id,
            TenantMember.tenant_id == tenant_id,
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "not_a_member", "message": "You are not a member of this tenant"},
        )
    return membership
