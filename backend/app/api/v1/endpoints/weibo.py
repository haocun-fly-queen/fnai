"""微博 HTTP 端点（阶段 5 — 微博对接）。

直接复用 E:\发文章 中已调通的微博发布逻辑。
端点"瘦"：接参 → 调 service → 翻译错误 → HTTP 响应。

端点列表：
    POST   /weibo/weibo-configs                     创建微博配置
    GET    /weibo/weibo-configs                     列出微博配置
    PUT    /weibo/weibo-configs/{id}                更新微博配置
    DELETE /weibo/weibo-configs/{id}                删除微博配置
    POST   /weibo/articles/{id}/publish-weibo       发布文章到微博
    GET    /weibo/publish-weibo/status/{publish_id}  查询发布状态
    POST   /weibo/verify-cookie                     验证 Cookie 是否有效
"""

import logging
import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_active_tenant_id, get_current_user, get_db, require_role
from app.core.config_crypto import decrypt_config, encrypt_config
from app.models.article import Article
from app.models.membership import Role, TenantMember
from app.models.publish_log import PublishLog, PublishStatus
from app.models.publish_target import PublishTarget, PublishTargetType
from app.models.user import User
from app.schemas.weibo import (
    WeiboConfigCreate,
    WeiboConfigResponse,
    WeiboConfigUpdate,
    WeiboPublishRequest,
    WeiboPublishResponse,
    WeiboPublishStatusResponse,
)
from app.services.weibo import (
    WeiboCookieExpired,
    WeiboError,
    WeiboPublishFailed,
    mask_cookie,
    publish_weibo,
    verify_cookie,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["weibo"])


# ============================================================
# 发布端点
# ============================================================


@router.post(
    "/articles/{article_id}/publish-weibo",
    response_model=WeiboPublishResponse,
    summary="发布文章到微博",
)
async def publish_to_weibo(
    article_id: UUID,
    request: WeiboPublishRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
) -> WeiboPublishResponse:
    """发布文章到微博。

    流程：
    1. 验证文章存在且属于当前租户
    2. 获取微博配置（Cookie）
    3. 调用微博 API 发布
    4. 记录发布日志
    """
    tenant_id = membership.tenant_id

    # 1. 查询文章
    stmt = select(Article).where(
        Article.id == article_id,
        Article.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    if not article.content:
        raise HTTPException(status_code=400, detail="文章内容为空，无法发布")

    # 2. 获取微博配置
    weibo_config = await _get_weibo_config(db, tenant_id)
    if not weibo_config:
        raise HTTPException(
            status_code=400,
            detail="未配置微博账号，请先在微博配置页面添加",
        )

    # 解密敏感字段（cookie）
    wb_config = decrypt_config(weibo_config.type, weibo_config.config)
    cookie = wb_config.get("cookie", "")
    if not cookie:
        raise HTTPException(status_code=400, detail="微博 Cookie 为空，请重新配置")

    # 3. 构造微博内容
    content = request.content
    if not content:
        # 默认取文章标题 + 正文（去除 HTML 标签）
        text = re.sub(r"<[^>]+>", "", article.content)
        # 清理多余空白
        text = re.sub(r"\s+", " ", text).strip()
        # 微博正文限制约 2000 字，留一些空间给标题和尾部
        max_content_len = 1800
        if len(text) > max_content_len:
            text = text[:max_content_len] + "..."
        content = f"{article.title}\n\n{text}"

    # 追加尾部内容（话题标签等）
    suffix = request.suffix or wb_config.get("default_suffix", "")
    if suffix:
        content = f"{content}\n\n{suffix}"

    # 4. 创建发布日志
    publish_log = PublishLog(
        article_id=article_id,
        target_id=weibo_config.id,
        status=PublishStatus.PENDING,
        created_by=current_user.id,
    )
    db.add(publish_log)
    await db.commit()
    await db.refresh(publish_log)

    # 5. 调用微博 API 发布
    try:
        weibo_result = await publish_weibo(
            cookie=cookie,
            content=content,
            image_url=request.image_url,
        )

        # 更新发布日志为成功
        publish_log.status = PublishStatus.SUCCESS
        publish_log.remote_id = weibo_result.get("weibo_id", "")
        await db.commit()

        logger.info(
            f"Article published to Weibo: article_id={article_id}, "
            f"weibo_id={weibo_result.get('weibo_id')}"
        )

        return WeiboPublishResponse(
            success=True,
            message="微博发布成功",
            publish_id=str(publish_log.id),
            weibo_id=weibo_result.get("weibo_id"),
            weibo_url=weibo_result.get("weibo_url"),
        )

    except WeiboCookieExpired as e:
        publish_log.status = PublishStatus.FAILED
        publish_log.error_message = e.message
        await db.commit()

        return WeiboPublishResponse(
            success=False,
            message=e.message,
            publish_id=str(publish_log.id),
        )

    except WeiboPublishFailed as e:
        publish_log.status = PublishStatus.FAILED
        publish_log.error_message = e.message
        await db.commit()

        return WeiboPublishResponse(
            success=False,
            message=e.message,
            publish_id=str(publish_log.id),
        )

    except WeiboError as e:
        publish_log.status = PublishStatus.FAILED
        publish_log.error_message = e.message
        await db.commit()

        return WeiboPublishResponse(
            success=False,
            message=e.message,
            publish_id=str(publish_log.id),
        )


@router.get(
    "/publish-weibo/status/{publish_id}",
    response_model=WeiboPublishStatusResponse,
    summary="查询微博发布状态",
)
async def get_publish_status(
    publish_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
) -> WeiboPublishStatusResponse:
    """查询微博发布状态。"""
    tenant_id = membership.tenant_id

    stmt = select(PublishLog).where(
        PublishLog.id == publish_id,
    )
    result = await db.execute(stmt)
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="发布记录不存在")

    return WeiboPublishStatusResponse(
        publish_id=publish_id,
        status=log.status.value if hasattr(log.status, "value") else str(log.status),
        weibo_id=log.remote_id,
        weibo_url=f"https://m.weibo.cn/detail/{log.remote_id}" if log.remote_id else None,
        fail_reason=log.error_message,
    )


@router.post(
    "/verify-cookie",
    summary="验证微博 Cookie 是否有效",
)
async def verify_weibo_cookie(
    request: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
):
    """验证微博 Cookie 是否有效，返回用户信息。"""
    cookie = request.get("cookie", "")
    if not cookie:
        raise HTTPException(status_code=400, detail="Cookie 不能为空")

    try:
        user_info = await verify_cookie(cookie)
        return {"valid": True, "user": user_info}
    except WeiboCookieExpired:
        return {"valid": False, "message": "Cookie 已过期，请重新获取"}
    except WeiboError as e:
        return {"valid": False, "message": e.message}


# ============================================================
# 配置管理端点
# ============================================================


@router.post(
    "/weibo-configs",
    response_model=WeiboConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建微博配置",
)
async def create_weibo_config(
    request: WeiboConfigCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
) -> WeiboConfigResponse:
    """创建微博配置。每个租户可以有多个微博配置。"""
    tenant_id = membership.tenant_id

    # 创建配置（加密 cookie 后存储）
    config = PublishTarget(
        tenant_id=tenant_id,
        name=request.name,
        type=PublishTargetType.WEIBO,
        config=encrypt_config(
            PublishTargetType.WEIBO,
            {
                "cookie": request.cookie,
                "default_suffix": request.default_suffix or "",
                "platform": "weibo",
            },
        ),
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    return WeiboConfigResponse(
        id=config.id,
        name=config.name,
        cookie_preview=mask_cookie(request.cookie),
        default_suffix=request.default_suffix,
        is_active=config.is_active,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


@router.get(
    "/weibo-configs",
    response_model=list[WeiboConfigResponse],
    summary="列出微博配置",
)
async def list_weibo_configs(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
) -> list[WeiboConfigResponse]:
    """列出当前租户的微博配置。"""
    tenant_id = membership.tenant_id

    stmt = select(PublishTarget).where(
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type == PublishTargetType.WEIBO,
    )
    result = await db.execute(stmt)
    configs = list(result.scalars().all())

    result_items = []
    for c in configs:
        # 解密后再生成脱敏预览
        decrypted = decrypt_config(c.type, c.config)
        result_items.append(
            WeiboConfigResponse(
                id=c.id,
                name=c.name,
                cookie_preview=mask_cookie(decrypted.get("cookie", "")),
                default_suffix=decrypted.get("default_suffix"),
                is_active=c.is_active,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
            )
        )
    return result_items


@router.put(
    "/weibo-configs/{config_id}",
    response_model=WeiboConfigResponse,
    summary="更新微博配置",
)
async def update_weibo_config(
    config_id: UUID,
    request: WeiboConfigUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
) -> WeiboConfigResponse:
    """更新微博配置。"""
    tenant_id = membership.tenant_id

    stmt = select(PublishTarget).where(
        PublishTarget.id == config_id,
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type == PublishTargetType.WEIBO,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="微博配置不存在")

    if request.name is not None:
        config.name = request.name

    new_config = dict(config.config)
    if request.cookie is not None:
        new_config["cookie"] = request.cookie  # 明文，稍后统一加密
    if request.default_suffix is not None:
        new_config["default_suffix"] = request.default_suffix
    # 加密敏感字段后整体赋值（encrypt_config 幂等）
    config.config = encrypt_config(config.type, new_config)

    await db.commit()
    await db.refresh(config)

    # 响应中的 cookie 预览：解密后再脱敏
    decrypted = decrypt_config(config.type, config.config)
    return WeiboConfigResponse(
        id=config.id,
        name=config.name,
        cookie_preview=mask_cookie(decrypted.get("cookie", "")),
        default_suffix=decrypted.get("default_suffix"),
        is_active=config.is_active,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


@router.delete(
    "/weibo-configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除微博配置",
)
async def delete_weibo_config(
    config_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
) -> None:
    """删除微博配置。"""
    tenant_id = membership.tenant_id

    stmt = select(PublishTarget).where(
        PublishTarget.id == config_id,
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type == PublishTargetType.WEIBO,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=404, detail="微博配置不存在")

    await db.delete(config)
    await db.commit()


# ============================================================
# 内部辅助函数
# ============================================================


async def _get_weibo_config(
    db: AsyncSession, tenant_id: UUID
) -> PublishTarget | None:
    """获取微博配置。"""
    stmt = select(PublishTarget).where(
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.is_active == True,  # noqa: E712
        PublishTarget.type == PublishTargetType.WEIBO,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
