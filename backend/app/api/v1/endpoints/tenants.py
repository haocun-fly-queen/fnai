"""Tenant HTTP 端点：列出我的租户、切换激活租户。

本文件是 tenants 相关操作的 HTTP 入口。逻辑分两层：
  - 端点层（本文件）：接参、调 service、翻译异常为 HTTP 状态码
  - service 层（services/tenant.py）：实际业务逻辑

学习要点：
- FastAPI 用 @router.get/@router.post 装饰器定义端点
- 端点函数应该是"瘦"的——只做参数接收和响应包装
- 异常处理：业务异常 → 4xx，未知异常 → 500
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.tenant import (
    MyTenantsResponse,
    TenantSwitchRequest,
    TenantSwitchResponse,
)
from app.services import tenant as tenant_service
from app.services.tenant import TenantError

# ============================================================
# 路由配置
# ============================================================
# prefix="/tenants" 表示下面所有路由都以 /api/v1/tenants 开头
# tags=["tenants"] 是 OpenAPI 文档的分组（Swagger UI 会按 tag 分组展示）
router = APIRouter(prefix="/tenants", tags=["tenants"])


# ============================================================
# 工具函数：把业务异常翻译成 HTTP 异常
# ============================================================


def _tenant_error_to_http(err: TenantError) -> HTTPException:
    """把 TenantError 翻译成合适的 HTTP 状态码。

    错误码 → HTTP 状态码的映射：
      - tenant_not_found → 404 Not Found
      - not_a_member      → 403 Forbidden
      - tenant_inactive   → 409 Conflict
      - 其他              → 400 Bad Request

    为什么这样映射：
    - 404：资源（租户）不存在，RESTful 语义最准确
    - 403：你没有权限访问这个资源（不是成员）
    - 409：资源状态冲突（租户被停用，不能切）
    - 400：兜底，参数错或未知业务错误
    """
    code = err.code
    # ⚠️ 注意：HTTPException 的 detail 是个 dict，前端会原样拿到
    # 我们的格式：{"code": "tenant_not_found", "message": "..."}
    if code == "tenant_not_found":
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": code, "message": err.message},
        )
    if code == "not_a_member":
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": code, "message": err.message},
        )
    if code == "tenant_inactive":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": code, "message": err.message},
        )
    # 兜底
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": err.message},
    )


# ============================================================
# 端点 1：列出我加入的所有租户
# ============================================================


@router.get(
    "/mine",
    response_model=MyTenantsResponse,
    summary="List all tenants the current user is a member of",
)
async def list_my_tenants(
    # Annotated[类型, Depends(...)] 是 FastAPI 的依赖注入语法
    # current: User = get_current_user() 的"类型安全版"
    # 效果：这个端点会自动从 Authorization 头里解 token，拿到 User 对象
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MyTenantsResponse:
    """GET /api/v1/tenants/mine

    返回当前用户加入的所有租户，按加入时间倒序。
    active_tenant_id 字段告诉前端"当前激活的是哪个"。

    业务用途：
    - 前端登录后跳 dashboard 时调一次，渲染 workspace 切换器
    - 前端切换租户后调一次，刷新 is_active 标记
    """
    # 1. 调 service 拿租户列表
    items = await tenant_service.list_my_tenants(db, current)

    # 2. 从当前 access token 里解出 active_tenant_id
    # 注意：get_current_user 没有把 active_tenant_id 暴露出来
    # 我们这里先返回 None 让前端用 zustand 里的 activeTenantId
    # TODO 优化：让 get_current_user 返回 (user, active_tenant_id) 元组
    return MyTenantsResponse(
        items=items,
        active_tenant_id=None,  # 前端自己用 store 里的值
    )


# ============================================================
# 端点 2：切换激活租户
# ============================================================


@router.post(
    "/switch",
    response_model=TenantSwitchResponse,
    summary="Switch the current user's active tenant",
)
async def switch_tenant(
    # 1. 请求体：必须是 Pydantic 模型，FastAPI 自动校验
    payload: TenantSwitchRequest,
    # 2. 当前用户：自动从 Bearer token 解出来
    current: Annotated[User, Depends(get_current_user)],
    # 3. DB session：自动注入
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TenantSwitchResponse:
    """POST /api/v1/tenants/switch

    客户端传 { "tenant_id": "uuid" }，后端校验后：
    1. 重新签发 access token，payload 里的 active_tenant_id 是新租户
    2. 重新签发 refresh token（让旧 refresh token 失效的简化处理）
    3. 返回新 token pair + 新租户的完整信息

    业务用途：
    - 前端 workspace 切换器点击切换时调
    - 切换成功后，前端要：
      a) 更新 zustand store 里的 token 和 activeTenantId
      b) 重新拉一次 /auth/me 刷新用户状态
    """
    try:
        result = await tenant_service.switch_active_tenant(
            db,
            user=current,
            target_tenant_id=payload.tenant_id,
        )
    except TenantError as exc:
        # 业务异常 → 翻译成 4xx HTTP
        raise _tenant_error_to_http(exc) from exc

    # 用 Pydantic 序列化响应
    # 这里需要把 dict 转成 TenantPublic
    from app.schemas.tenant import TenantPublic

    return TenantSwitchResponse(
        access_token=result["access_token"],
        refresh_token=result["refresh_token"],
        token_type="bearer",
        expires_in=result["expires_in"],
        active_tenant=TenantPublic(**result["active_tenant"]),
    )
