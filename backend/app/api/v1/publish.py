"""发布端点（阶段 5）—— 发布目标管理 + 文章发布。

发布目标 CRUD：
    POST   /publish-targets          创建发布目标
    GET    /publish-targets          列出发布目标
    GET    /publish-targets/{id}     查看单个
    PUT    /publish-targets/{id}     更新
    DELETE /publish-targets/{id}     删除

文章发布：
    POST   /articles/{id}/publish    发布到指定目标
    GET    /articles/{id}/publish-logs  查看发布历史
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_active_tenant_id, get_current_user, get_db
from app.models.article import Article
from app.models.publish_log import PublishLog, PublishStatus
from app.models.publish_target import PublishTarget, PublishTargetType
from app.models.user import User
from app.schemas.publish import (
    PublishLogResponse,
    PublishLogSimpleResponse,
    PublishRequest,
    PublishResponse,
    PublishTargetCreate,
    PublishTargetResponse,
    PublishTargetUpdate,
)
from app.services.wordpress import WordPressClient

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================
# 发布目标 CRUD
# ============================================================


@router.post("/publish-targets", response_model=PublishTargetResponse, status_code=201)
async def create_publish_target(
    data: PublishTargetCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
) -> PublishTarget:
    """创建发布目标（WordPress / Webhook）。"""
    target = PublishTarget(
        tenant_id=tenant_id,
        name=data.name,
        type=data.type,
        config=data.config,
        is_active=data.is_active,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return target


@router.get("/publish-targets", response_model=list[PublishTargetResponse])
async def list_publish_targets(
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
    active_only: bool = True,
) -> list[PublishTarget]:
    """列出发布目标（租户隔离）。

    注意：微信公众号（wechat_mp）有独立的发布入口和配置页，
    这里只返回 WordPress / Webhook 目标，避免污染通用发布下拉框。
    """
    stmt = select(PublishTarget).where(
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type != PublishTargetType.WECHAT_MP,
    )
    if active_only:
        stmt = stmt.where(PublishTarget.is_active == True)  # noqa: E712
    stmt = stmt.order_by(PublishTarget.created_at.desc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/publish-targets/{target_id}", response_model=PublishTargetResponse)
async def get_publish_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
) -> PublishTarget:
    """查看单个发布目标。"""
    stmt = select(PublishTarget).where(
        PublishTarget.id == target_id,
        PublishTarget.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="发布目标不存在")

    return target


@router.put("/publish-targets/{target_id}", response_model=PublishTargetResponse)
async def update_publish_target(
    target_id: UUID,
    data: PublishTargetUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
) -> PublishTarget:
    """更新发布目标。"""
    stmt = select(PublishTarget).where(
        PublishTarget.id == target_id,
        PublishTarget.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="发布目标不存在")

    # 更新字段
    if data.name is not None:
        target.name = data.name
    if data.config is not None:
        target.config = data.config
    if data.is_active is not None:
        target.is_active = data.is_active

    await db.commit()
    await db.refresh(target)
    return target


@router.delete("/publish-targets/{target_id}", status_code=204)
async def delete_publish_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
) -> None:
    """删除发布目标（级联删除发布日志）。"""
    stmt = select(PublishTarget).where(
        PublishTarget.id == target_id,
        PublishTarget.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="发布目标不存在")

    await db.delete(target)
    await db.commit()


# ============================================================
# 文章发布
# ============================================================


@router.post("/articles/{article_id}/publish", response_model=PublishResponse)
async def publish_article(
    article_id: UUID,
    data: PublishRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
    current_user: User = Depends(get_current_user),
) -> PublishResponse:
    """发布文章到指定目标（WordPress / Webhook）。"""
    # 1. 查询文章
    stmt = select(Article).where(Article.id == article_id, Article.tenant_id == tenant_id)
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    if not article.content:
        raise HTTPException(status_code=400, detail="文章内容为空，无法发布")

    # 2. 查询发布目标
    stmt = select(PublishTarget).where(
        PublishTarget.id == data.target_id,
        PublishTarget.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="发布目标不存在")

    if not target.is_active:
        raise HTTPException(status_code=400, detail="发布目标已禁用")

    # 3. 创建发布日志（初始状态 pending）
    log = PublishLog(
        article_id=article_id,
        target_id=data.target_id,
        status=PublishStatus.PENDING,
        created_by=current_user.id,
    )
    db.add(log)
    await db.commit()
    await db.refresh(log)

    # 4. 根据目标类型调用相应的发布逻辑
    try:
        action = "created"
        if target.type == PublishTargetType.WORDPRESS:
            remote_id, action = await _publish_to_wordpress(article, target, data.status, db)
        elif target.type == PublishTargetType.WEBHOOK:
            remote_id = await _publish_to_webhook(article, target)
        else:
            raise ValueError(f"不支持的发布目标类型: {target.type}")

        # 5. 更新日志为成功
        log.status = PublishStatus.SUCCESS
        log.remote_id = str(remote_id)
        await db.commit()

        msg = "更新成功" if action == "updated" else "发布成功"
        return PublishResponse(
            success=True,
            message=msg,
            remote_id=str(remote_id),
            log_id=log.id,
            action=action,
        )

    except Exception as e:
        # 6. 发布失败，记录错误
        logger.error(f"发布失败: {e}", exc_info=True)
        log.status = PublishStatus.FAILED
        log.error_message = str(e)
        await db.commit()

        return PublishResponse(
            success=False,
            message=f"发布失败: {str(e)}",
            log_id=log.id,
        )


async def _publish_to_wordpress(
    article: Article, target: PublishTarget, status: str, db: AsyncSession
) -> tuple[int, str]:
    """发布到 WordPress。

    如果该文章已发布到同一目标（有成功的 remote_id），则更新远程文章；
    否则创建新文章。

    Returns:
        (post_id, action) — action 为 "created" 或 "updated"
    """
    config = target.config
    required_keys = ["site_url", "username", "app_password"]
    missing = [k for k in required_keys if k not in config]
    if missing:
        raise ValueError(f"WordPress 配置缺少字段: {', '.join(missing)}")

    client = WordPressClient(
        site_url=config["site_url"],
        username=config["username"],
        app_password=config["app_password"],
    )

    # 查询是否已发布到同一目标
    existing_stmt = (
        select(PublishLog)
        .where(
            PublishLog.article_id == article.id,
            PublishLog.target_id == target.id,
            PublishLog.status == PublishStatus.SUCCESS,
            PublishLog.remote_id.isnot(None),
        )
        .order_by(PublishLog.published_at.desc())
        .limit(1)
    )
    result = await db.execute(existing_stmt)
    prev_log = result.scalars().first()

    if prev_log and prev_log.remote_id:
        # 已发布过 → 更新远程文章
        post_id = await client.update_post(
            post_id=int(prev_log.remote_id),
            title=article.title or "未命名文章",
            content=article.content,
            status=status,
        )
        return post_id, "updated"
    else:
        # 首次发布 → 创建新文章
        post_id = await client.create_post(
            title=article.title or "未命名文章",
            content=article.content,
            status=status,
        )
        return post_id, "created"


async def _publish_to_webhook(article: Article, target: PublishTarget) -> str:
    """发布到自定义 Webhook。"""
    import httpx

    config = target.config
    webhook_url = config.get("webhook_url")
    if not webhook_url:
        raise ValueError("Webhook 配置缺少 webhook_url")

    headers = config.get("headers", {})

    # 获取摘要（从 seo_meta 或为空）
    summary = ""
    if article.seo_meta and isinstance(article.seo_meta, dict):
        summary = article.seo_meta.get("description", "")

    payload = {
        "title": article.title,
        "content": article.content,
        "summary": summary,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(webhook_url, json=payload, headers=headers)
        response.raise_for_status()
        # 返回响应体作为 remote_id（简化处理）
        return response.text[:200]


@router.get("/articles/{article_id}/publish-logs", response_model=list[PublishLogSimpleResponse])
async def get_publish_logs(
    article_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
) -> list[PublishLogSimpleResponse]:
    """查看文章的发布历史（简化版）。

    会自动更新微信发布的状态（如果是待审核状态）。
    """
    # 验证文章存在且属于当前租户
    stmt = select(Article).where(Article.id == article_id, Article.tenant_id == tenant_id)
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    # 查询发布日志（关联 target 以获取完整对象）
    stmt = (
        select(PublishLog, PublishTarget)
        .join(PublishTarget, PublishLog.target_id == PublishTarget.id)
        .where(PublishLog.article_id == article_id)
        .order_by(PublishLog.published_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    # 对于微信发布且状态为 PENDING 的记录，尝试更新状态
    from app.services.wechat_mp import WechatMpClient

    for log, target in rows:
        if (
            target.type == PublishTargetType.WECHAT_MP
            and log.status == PublishStatus.PENDING
            and log.remote_id
        ):
            try:
                client = WechatMpClient(
                    db=db,
                    app_id=target.config["app_id"],
                    app_secret=target.config["app_secret"],
                )
                status_data = await client.get_publish_status(log.remote_id)
                wechat_status = status_data.get("publish_status", 1)

                # 微信发布状态：0/3 = 成功，2 = 失败，1 = 审核中
                if wechat_status in (0, 3):
                    log.status = PublishStatus.SUCCESS
                    log.published_at = datetime.utcnow()
                    await db.commit()
                    logger.info(f"Auto-updated PublishLog {log.id} to SUCCESS")
                elif wechat_status == 2:
                    log.status = PublishStatus.FAILED
                    log.error_message = status_data.get("fail_reason", "微信审核失败")
                    await db.commit()
                    logger.info(f"Auto-updated PublishLog {log.id} to FAILED")
            except Exception as e:
                logger.warning(f"Failed to update wechat status for log {log.id}: {e}")
                # 失败不影响返回结果，继续处理

    # 转换为简化响应
    return [
        PublishLogSimpleResponse(
            is_published=(log.status == PublishStatus.SUCCESS),
            published_at=log.published_at,
            target_name=target.name,
            target_id=target.id,
        )
        for log, target in rows
    ]
