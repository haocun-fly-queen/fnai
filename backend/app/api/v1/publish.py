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
from app.core.config_crypto import decrypt_config, encrypt_config, mask_config
from app.core.url_validator import URLValidationError, validate_webhook_url, validate_wordpress_url
from app.models.article import Article
from app.models.publish_log import PublishLog, PublishStatus
from app.models.publish_target import PublishTarget, PublishTargetType
from app.models.user import User
from app.schemas.publish import (
    BatchPublishRequest,
    BatchPublishResponse,
    PublishLogResponse,
    PublishLogSimpleResponse,
    PublishRequest,
    PublishResponse,
    PublishTargetCreate,
    PublishTargetResponse,
    PublishTargetUpdate,
)
from app.services.publishers import PublishResult, get_publisher
from app.services.wordpress import WordPressClient

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================
# 发布目标 CRUD
# ============================================================


async def _validate_publish_target_config(target_type: PublishTargetType, config: dict) -> None:
    """验证发布目标配置，包括 URL 安全性检查。

    委托给对应平台的 Publisher 插件验证（plugin 化重构后）。

    Args:
        target_type: 发布目标类型（可能是 schema 枚举或 model 枚举）
        config: 配置字典

    Raises:
        HTTPException: 配置无效或 URL 不安全
    """
    try:
        # 统一转成 model 枚举（schema 用小写 wordpress，model 用大写 WORDPRESS）
        model_type = _to_model_enum(target_type)
        publisher = get_publisher(model_type)
        await publisher.validate_config(config)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _to_model_enum(target_type: PublishTargetType) -> PublishTargetType:
    """把 schema 枚举（小写）转成 model 枚举（大写）。"""
    type_str = str(target_type.value) if hasattr(target_type, "value") else str(target_type)
    # model 枚举是大写：WORDPRESS, WEBHOOK, WECHAT_MP, WEIBO
    return PublishTargetType(type_str.upper())


def _to_masked_response(target: PublishTarget) -> PublishTargetResponse:
    """构造脱敏的发布目标响应（隐藏 config 中的敏感字段）。

    注意：API 响应绝不返回明文/密文敏感字段，统一替换为 "******"。
    """
    return PublishTargetResponse(
        id=target.id,
        tenant_id=target.tenant_id,
        name=target.name,
        type=target.type,
        config=mask_config(target.type, target.config),
        is_active=target.is_active,
        created_at=target.created_at,
        updated_at=target.updated_at,
    )


@router.post("/publish-targets", response_model=PublishTargetResponse, status_code=201)
async def create_publish_target(
    data: PublishTargetCreate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
) -> PublishTargetResponse:
    """创建发布目标（WordPress / Webhook）。

    安全特性：
        - 验证 URL 格式和安全性（防止 SSRF 攻击）
        - 拒绝内网地址（127.x, 10.x, 192.168.x, 172.16-31.x, 169.254.x）
        - 敏感字段（app_password 等）加密后存储
        - 响应中脱敏敏感字段
    """
    # 验证配置（包括 URL 安全性）
    await _validate_publish_target_config(data.type, data.config)

    target = PublishTarget(
        tenant_id=tenant_id,
        name=data.name,
        type=data.type,
        config=encrypt_config(data.type, data.config),  # 加密敏感字段后存储
        is_active=data.is_active,
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)
    return _to_masked_response(target)


@router.get("/publish-targets", response_model=list[PublishTargetResponse])
async def list_publish_targets(
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
    active_only: bool = True,
) -> list[PublishTargetResponse]:
    """列出发布目标（租户隔离）。

    注意：微信公众号（wechat_mp）有独立的发布入口和配置页，
    这里只返回 WordPress / Webhook 目标，避免污染通用发布下拉框。
    响应中脱敏敏感字段。
    """
    stmt = select(PublishTarget).where(
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type != PublishTargetType.WECHAT_MP,
    )
    if active_only:
        stmt = stmt.where(PublishTarget.is_active == True)  # noqa: E712
    stmt = stmt.order_by(PublishTarget.created_at.desc())

    result = await db.execute(stmt)
    return [_to_masked_response(t) for t in result.scalars().all()]


@router.get("/publish-targets/{target_id}", response_model=PublishTargetResponse)
async def get_publish_target(
    target_id: UUID,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
) -> PublishTargetResponse:
    """查看单个发布目标（响应脱敏）。"""
    stmt = select(PublishTarget).where(
        PublishTarget.id == target_id,
        PublishTarget.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    target = result.scalar_one_or_none()

    if not target:
        raise HTTPException(status_code=404, detail="发布目标不存在")

    return _to_masked_response(target)


@router.put("/publish-targets/{target_id}", response_model=PublishTargetResponse)
async def update_publish_target(
    target_id: UUID,
    data: PublishTargetUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
) -> PublishTargetResponse:
    """更新发布目标。

    安全特性：
        - 如果更新 config，重新验证 URL 安全性（防止 SSRF 攻击）
        - 敏感字段加密后存储
        - 响应中脱敏敏感字段
    """
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
        # 验证新配置的安全性
        await _validate_publish_target_config(target.type, data.config)
        # 加密敏感字段后整体赋值（触发 SQLAlchemy JSONB 变更检测）
        target.config = encrypt_config(target.type, data.config)
    if data.is_active is not None:
        target.is_active = data.is_active

    await db.commit()
    await db.refresh(target)
    return _to_masked_response(target)


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

    # 4. 通过插件 registry 调用平台发布逻辑
    try:
        publisher = get_publisher(target.type)
        config = decrypt_config(target.type, target.config)
        options = {"status": data.status}  # 平台通用选项

        result: PublishResult = await publisher.publish(
            article=article,
            config=config,
            options=options,
            db=db,
            target_id=target.id,
        )

        # 5. 更新日志
        if result.success:
            log.status = PublishStatus.SUCCESS
            log.remote_id = result.remote_id
            await db.commit()

            action = result.metadata.get("action", "created")
            msg = "更新成功" if action == "updated" else "发布成功"
            return PublishResponse(
                success=True,
                message=msg,
                remote_id=result.remote_id,
                log_id=log.id,
                action=action,
            )
        else:
            log.status = PublishStatus.FAILED
            log.error_message = result.message
            await db.commit()

            return PublishResponse(
                success=False,
                message=result.message,
                log_id=log.id,
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


@router.post("/articles/batch-publish", response_model=BatchPublishResponse)
async def batch_publish_articles(
    data: BatchPublishRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
    current_user: User = Depends(get_current_user),
) -> BatchPublishResponse:
    """批量发布：把多篇文章发布到多个目标。

    同步校验文章/目标归属当前租户，然后为每个 (文章, 目标) 组合
    异步投递一个 Celery 任务。前端轮询各文章的 publish-logs 查看状态。
    """
    from app.workers.tasks import batch_publish_task

    # 1. 校验文章：全部属于当前租户
    article_stmt = select(Article.id).where(
        Article.id.in_(data.article_ids),
        Article.tenant_id == tenant_id,
    )
    result = await db.execute(article_stmt)
    valid_article_ids = set(result.scalars().all())

    missing_articles = set(data.article_ids) - valid_article_ids
    if missing_articles:
        raise HTTPException(
            status_code=404,
            detail=f"文章不存在或无权访问: {', '.join(str(a) for a in missing_articles)}",
        )

    # 2. 校验目标：全部属于当前租户且已启用
    target_stmt = select(PublishTarget).where(
        PublishTarget.id.in_(data.target_ids),
        PublishTarget.tenant_id == tenant_id,
    )
    result = await db.execute(target_stmt)
    targets = result.scalars().all()
    valid_target_ids = {t.id for t in targets}

    missing_targets = set(data.target_ids) - valid_target_ids
    if missing_targets:
        raise HTTPException(
            status_code=404,
            detail=f"发布目标不存在或无权访问: {', '.join(str(t) for t in missing_targets)}",
        )

    inactive = [t.name for t in targets if not t.is_active]
    if inactive:
        raise HTTPException(
            status_code=400,
            detail=f"发布目标已禁用: {', '.join(inactive)}",
        )

    # 3. 为每个 (文章, 目标) 组合投递异步任务
    task_count = 0
    for article_id in data.article_ids:
        for target_id in data.target_ids:
            batch_publish_task.delay(
                str(article_id),
                str(target_id),
                data.status,
                str(current_user.id),
            )
            task_count += 1

    logger.info(
        "Batch publish: tenant=%s articles=%d targets=%d tasks=%d",
        tenant_id, len(data.article_ids), len(data.target_ids), task_count,
    )

    return BatchPublishResponse(
        task_count=task_count,
        article_ids=list(data.article_ids),
        message=f"已提交 {task_count} 个发布任务（{len(data.article_ids)} 篇 × {len(data.target_ids)} 个目标）",
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
    # 解密敏感字段（app_password）
    config = decrypt_config(target.type, target.config)
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
    """发布到自定义 Webhook。

    安全特性：
        - 再次验证 webhook_url（防止配置被篡改或绕过验证）
    """
    import httpx

    # 解密敏感字段（headers）
    config = decrypt_config(target.type, target.config)
    webhook_url = config.get("webhook_url")
    if not webhook_url:
        raise ValueError("Webhook 配置缺少 webhook_url")

    # 验证 URL 安全性（双重保险）
    try:
        webhook_url = validate_webhook_url(webhook_url)
    except URLValidationError as e:
        raise ValueError(f"Webhook URL 不安全: {e.message}")

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
                wc_config = decrypt_config(target.type, target.config)
                client = WechatMpClient(
                    db=db,
                    app_id=wc_config["app_id"],
                    app_secret=wc_config["app_secret"],
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
