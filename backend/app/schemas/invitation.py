"""邀请（Invitation）的请求/响应数据契约。

本文件用 Pydantic v2 定义 4 个端点的输入输出"形状"。

学习要点（给 Java 背景的同事）：
- BaseModel ≈ Java 的 record（不可变数据载体）
- Field(min_length=...) ≈ @Size(min, max)
- EmailStr ≈ @Email + 自动校验格式
- ConfigDict(from_attributes=True) ≈ Jackson 的 @JsonAutoDetect
  （让 Pydantic 能从 ORM 对象直接构造）
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.membership import Role

# ============================================================
# 1. 创建邀请的请求体
# ============================================================


class CreateInvitationRequest(BaseModel):
    """POST /invitations 的请求体。

    ⚠️ 故意不带 tenant_id：
    tenant_id 必须从 access token 里的 active_tenant_id 拿。
    防止前端发个 "tenant_id=别人的ID"，绕过 active tenant 检查。
    """

    # 被邀请者邮箱
    # EmailStr 自动校验格式：必须是 "xxx@yyy.zzz" 形式
    email: EmailStr = Field(
        description="被邀请者的邮箱（接受邀请时要用这个账号登录）",
        examples=["lilei@example.com"],
    )

    # 给什么角色
    # 默认 MEMBER（最常见：邀请同事一起干活）
    # ⚠️ 安全：业务上不允许 Role.OWNER（不能让被邀请者当老板）
    # 这个校验在 service 层做，不在 schema 层
    role: Role = Field(
        default=Role.MEMBER,
        description="接受后给什么角色：ADMIN / MEMBER / VIEWER（不允许 OWNER）",
    )


# ============================================================
# 2. 邀请的公开信息（响应）
# ============================================================


class InvitationPublic(BaseModel):
    """GET /invitations 和 POST /invitations 的响应。

    给前端展示用的"展示数据"，不暴露内部细节（如 token）。
    等等——这里要不要带 token？看下面 ↓
    """

    # ---------- 基础字段 ----------

    id: UUID
    email: str
    role: str  # PG ENUM 序列化成字符串
    status: str  # pending / accepted / expired / revoked（派生字段，service 层组装）

    # 时间字段
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None

    # 邀请人信息（嵌套对象）
    invited_by_email: str | None = Field(
        default=None,
        description="邀请人的邮箱（邀请人账号被删了就是 None）",
    )

    # ⚠️ 关键：是否带 token / invite_link 取决于"是谁在请求"
    #  - ADMIN/OWNER 在列表里看到的是 "完整链接"，方便复制
    #  - 接受邀请的端点（公开）只接收 token，不返回
    # 用 model_config 控制：
    model_config = ConfigDict(from_attributes=True)


class InvitationCreateResponse(BaseModel):
    """POST /invitations 的响应（创建后立刻返回）。

    ⚠️ 关键区别：只在这里返回 invite_link / token
    原因：链接要"新鲜"的，发邮件/IM 时用。
    列表接口不返回（避免泄露在 dashboard 上）。
    """

    invitation: InvitationPublic
    # 完整 URL，前端能直接复制发出去
    # ⚠️ 这个 URL 是后端组装的，前端不要自己拼（避免域名/路径不一致）
    invite_link: str = Field(
        description="完整的接受邀请 URL，例：'https://app.fnai.com/invitations/accept?token=xxx'",
    )
    # 纯 token（如果前端要做二维码 / 其他渠道）
    token: str = Field(
        description="纯 token（不含 URL），用于二维码等场景",
    )


# ============================================================
# 3. 接受邀请的请求体
# ============================================================


class AcceptInvitationRequest(BaseModel):
    """POST /invitations/accept 的请求体。

    这个端点比较特殊：
    - 必须是登录用户才能调
    - 但 token 是公开的（在 URL 里 / 邮件里）
    - 还要校验 current_user.email == invitation.email
    """

    token: str = Field(
        min_length=20,  # 至少 20 字符（secrets.token_urlsafe(32) 至少 43 字符）
        max_length=64,  # 数据库 String(64)
        description="邀请 token，从邀请链接 / 邮件里获取",
    )


# ============================================================
# 4. 撤销邀请的请求体（其实可以走 URL）
# ============================================================
# 撤销比较简单：DELETE /invitations/{id}，body 为空
# 不需要单独的 Request schema

# ============================================================
# 5. 接受邀请成功后的响应
# ============================================================


class AcceptInvitationResponse(BaseModel):
    """POST /invitations/accept 的成功响应。

    接受后，前端需要：
    1. 跳到新工作空间的 dashboard
    2. 重新拉 /auth/me 更新 memberships
    3. 调 /tenants/switch 把 active tenant 切到新工作空间

    所以响应里直接返回新租户的信息，方便前端一次性处理。
    """

    # 接受成功的邀请记录
    invitation: InvitationPublic

    # 新加入的租户信息（前端直接渲染）
    joined_tenant: dict = Field(
        description="新加入的租户信息（包含 role，is_active=true）",
    )

    # 提示信息
    message: str = Field(
        default="Invitation accepted successfully",
        description="给前端展示的成功信息",
    )


# ============================================================
# 6. 列出邀请的响应包装
# ============================================================


class ListInvitationsResponse(BaseModel):
    """GET /invitations 的响应。

    包含：
    - 所有邀请（pending + 历史）
    - 当前 active_tenant_id（让前端知道"这是哪个租户的邀请"）
    """

    items: list[InvitationPublic] = Field(
        description="邀请列表，按创建时间倒序",
    )
    active_tenant_id: UUID | None = Field(
        default=None,
        description="当前激活的租户 ID（列表都是这个租户的）",
    )

    # 统计信息（前端可以显示"3 个待处理 / 5 个已接受"）
    pending_count: int = Field(
        default=0,
        description="待处理（未过期、未接受、未撤销）的邀请数",
    )
    accepted_count: int = Field(
        default=0,
        description="已被接受的邀请数",
    )
