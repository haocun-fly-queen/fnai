"""Membership（成员关系）相关的数据契约。

本文件定义"踢人/改角色"接口的请求/响应形状。

学习要点（给 Java 背景的同事）：
- 这些 schema 是"操作"接口（不是简单查询）
- 有请求体（PATCH/DELETE 用 query/body）
- 有响应体（确认操作结果）
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.membership import Role

# ============================================================
# 1. 成员详情（GET /tenants/{tenant_id}/members）
# ============================================================


class MemberDetail(BaseModel):
    """单个成员的完整信息。

    比 TenantWithMembership（schemas/tenant.py）多了：
    - joined_at: 什么时候加入这个租户
    - user.email, user.full_name: 用户的展示信息

    业务用途：团队管理页"成员列表"
    """

    model_config = ConfigDict(from_attributes=True)

    # 关系字段
    user_id: UUID
    role: Role

    # 用户信息（嵌套）
    user: dict = Field(
        description="用户基础信息：{ id, email, full_name, status }",
    )

    # 元数据
    joined_at: datetime = Field(
        description="加入这个租户的时间",
    )
    invited_by: UUID | None = Field(
        default=None,
        description="邀请人 user_id（直接注册的没有）",
    )

    # 派生标记：当前用户是不是 active tenant
    is_current_user: bool = Field(
        default=False,
        description="这个成员是不是当前请求的 user（用于前端隐藏自己的某些操作按钮）",
    )


class ListMembersResponse(BaseModel):
    """GET /tenants/{tenant_id}/members 响应。"""

    items: list[MemberDetail] = Field(
        description="按 role 倒序 + joined_at 升序：OWNER 排最前，新来的排最后",
    )
    total: int = Field(description="总成员数")


# ============================================================
# 2. 改角色（PATCH /tenants/{tenant_id}/members/{user_id}）
# ============================================================


class ChangeRoleRequest(BaseModel):
    """PATCH 请求体：把某成员改成什么角色。"""

    role: Role = Field(
        description="目标角色：ADMIN / MEMBER / VIEWER（不允许 OWNER）",
    )


# ============================================================
# 3. 踢人响应（DELETE /tenants/{tenant_id}/members/{user_id}）
# ============================================================


class RemoveMemberResponse(BaseModel):
    """DELETE 响应：确认被踢了 + 还剩多少人。"""

    removed_user_id: UUID
    remaining_count: int = Field(description="租户剩余成员数")
    message: str = Field(default="Member removed successfully")


# ============================================================
# 4. 改角色响应（PATCH 的响应）
# ============================================================


class ChangeRoleResponse(BaseModel):
    """PATCH 响应：确认角色改了。"""

    user_id: UUID
    old_role: Role
    new_role: Role
    message: str = Field(default="Role updated successfully")
