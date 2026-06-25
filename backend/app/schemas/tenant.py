"""Tenant 相关的数据契约（请求/响应 schema）。

本文件定义前端和后端之间"传递的租户数据"长什么样。
Pydantic v2 会根据这些 schema 自动：
  1. 校验请求体（缺字段、类型错、长度超限 → 422）
  2. 序列化响应体（ORM 对象 → JSON）
  3. 生成 OpenAPI 文档

学习要点：
- Pydantic v2 的 BaseModel ≈ Java 的 record + Bean Validation
- model_config = ConfigDict(from_attributes=True) 让它能从 ORM 对象生成
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.membership import Role

# ============================================================
# 单个租户的"展示数据"（前端能看到的所有字段）
# ============================================================


class TenantPublic(BaseModel):
    """返回给前端的单个租户信息。

    字段来源：tenants 表 + 关联的 membership 信息（角色、加入时间）

    为什么 membership 信息也塞进 tenant 里：
    前端做"workspace 切换器"时需要显示"我在这个租户的角色"，
    单独再发一次 /memberships 请求会浪费一次 RTT。
    """

    # 租户基础信息
    id: UUID
    name: str
    slug: str
    plan: str  # PG ENUM 序列化后是字符串
    status: str  # 同上

    # 当前用户在这个租户的身份
    role: Role  # OWNER / ADMIN / MEMBER / VIEWER
    is_active: bool = Field(
        default=False,
        description="是否当前激活的租户（同一时刻一个用户只能激活一个）",
    )

    created_at: datetime

    # Pydantic v2 配置：允许从 SQLAlchemy ORM 对象直接生成
    # 相当于 Java Jackson 的 @JsonAutoDetect
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# 切换租户的请求体
# ============================================================


class TenantSwitchRequest(BaseModel):
    """POST /tenants/switch 的请求体。

    客户端需要传一个 tenant_id 过来，我们去校验：
    1. 这个租户存不存在
    2. 当前用户是不是这个租户的成员
    3. 是不是有多个成员共享这个 active 状态（不会，但要做）

    校验通过后，我们会用新的 active_tenant_id 重新签发 access token。
    """

    tenant_id: UUID = Field(
        description="要切换到的目标租户 ID",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )


# ============================================================
# 切换租户的响应体
# ============================================================


class TenantSwitchResponse(BaseModel):
    """切换租户成功后返回新 token + 用户当前状态。

    为什么不只返回新 token：
    前端拿到新 token 之后要更新 zustand store 和 localStorage，
    顺便也返回一份 user + memberships 让前端能刷新 UI 缓存。
    """

    access_token: str = Field(description="新的 access token（active_tenant_id 已更新）")
    refresh_token: str = Field(description="新的 refresh token")
    token_type: str = Field(default="bearer", description="固定 'bearer'，OAuth 2.0 标准")
    expires_in: int = Field(description="access token 剩余秒数")

    # 顺手返回当前激活的租户信息，前端不用再发一次 /auth/me
    active_tenant: TenantPublic


# ============================================================
# 列出"我所在的全部租户"
# ============================================================


class MyTenantsResponse(BaseModel):
    """GET /tenants/mine 的响应体。"""

    items: list[TenantPublic] = Field(
        description="我作为成员加入的所有租户，按加入时间倒序",
    )
    active_tenant_id: UUID | None = Field(
        default=None,
        description="当前激活的租户 ID（如果还没选过，就是 None）",
    )
