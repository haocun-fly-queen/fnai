"""示例端点：演示 require_role 装饰器怎么用。

本文件是"测试桩"——专门用来验证权限检查装饰器是不是对的。
生产业务接口（documents/articles/...）会照这个模式写。

⚠️ 这个端点不暴露给生产用，做完权限验证后可以删。
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.v1.deps import get_active_membership, get_current_user, require_role
from app.models.membership import Role, TenantMember
from app.models.user import User

router = APIRouter(prefix="/demo", tags=["demo"])


class DemoResponse(BaseModel):
    """演示端点的响应——只返回我们想看的字段。"""

    user_email: str
    tenant_id: str
    role: str
    required_role: str
    message: str


@router.post(
    "/owner-only",
    response_model=DemoResponse,
    summary="Demo: requires OWNER role",
)
async def owner_only_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.OWNER))],
) -> DemoResponse:
    """只有 OWNER 能调。ADMIN/MEMBER/VIEWER 全被拒。

    等价 Java 写法：
        @PreAuthorize("hasRole('OWNER')")
        public Response upload(...) { ... }
    """
    return DemoResponse(
        user_email=user.email,
        tenant_id=str(membership.tenant_id),
        role=membership.role.value,
        required_role="owner",
        message="Welcome, owner! You can delete the tenant.",
    )


@router.post(
    "/admin-action",
    response_model=DemoResponse,
    summary="Demo: requires at least ADMIN role",
)
async def admin_action_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
) -> DemoResponse:
    """ADMIN 及以上能调（OWNER/ADMIN 通过，MEMBER/VIEWER 拒绝）。"""
    return DemoResponse(
        user_email=user.email,
        tenant_id=str(membership.tenant_id),
        role=membership.role.value,
        required_role="admin",
        message="You can invite/remove members.",
    )


@router.post(
    "/member-action",
    response_model=DemoResponse,
    summary="Demo: requires at least MEMBER role (any non-viewer)",
)
async def member_action_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
) -> DemoResponse:
    """MEMBER 及以上能调（OWNER/ADMIN/MEMBER 通过，VIEWER 拒绝）。"""
    return DemoResponse(
        user_email=user.email,
        tenant_id=str(membership.tenant_id),
        role=membership.role.value,
        required_role="member",
        message="You can upload documents and write articles.",
    )


@router.get(
    "/view-settings",
    response_model=DemoResponse,
    summary="Demo: any tenant member can view (uses get_active_membership)",
)
async def view_settings_endpoint(
    user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(get_active_membership)],
) -> DemoResponse:
    """任何成员都能看（OWNER/ADMIN/MEMBER/VIEWER 都通过）。"""
    return DemoResponse(
        user_email=user.email,
        tenant_id=str(membership.tenant_id),
        role=membership.role.value,
        required_role="viewer",
        message="Read-only access granted.",
    )
