"""API v1 router aggregation.

本文件是"路由总装车间"：把各个端点文件（auth、tenants、...）的 router
合并到一个主 router 上，注册到 FastAPI app。

学习要点：
- 拆分成多个 endpoint 文件而不是塞一起：方便多人并行开发、方便 review
- include_router 把每个子模块的路由"挂"到主 router
- 这里只做"组装"，不写任何业务逻辑
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    demo,
    health,
    invitations,
    knowledge,
    memberships,
    tenants,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(tenants.router)  # 租户相关端点
api_router.include_router(invitations.router)  # 邀请相关端点
api_router.include_router(memberships.router)  # 成员管理端点（踢人/改角色）
api_router.include_router(knowledge.router)  # 知识库（Step 1 占位）
api_router.include_router(demo.router)  # 演示 require_role 用法
