"""微信公众号 HTTP 端点（阶段 5 — 微信公众号对接）。

概念：微信公众号发布相关的 API 端点。
模块：api/v1/endpoints/wechat_mp.py
作用：提供微信公众号发布、状态查询、配置管理等接口
怎么写：
    - 端点"瘦"：接参 → 调 service → 翻译错误 → HTTP 响应
    - 复用现有的认证和权限机制
    - 完整的错误处理和日志记录

端点列表：
    POST   /articles/{id}/publish-wechat      发布文章到微信公众号
    GET    /publish-wechat/status/{publish_id} 查询发布状态
    POST   /wechat-configs                     创建微信公众号配置
    GET    /wechat-configs                     列出微信公众号配置
    PUT    /wechat-configs/{id}                更新微信公众号配置
    DELETE /wechat-configs/{id}                删除微信公众号配置
"""

import logging
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
from app.schemas.wechat import (
    WechatConfigCreate,
    WechatConfigResponse,
    WechatConfigUpdate,
    WechatMassSendRequest,
    WechatMassSendResponse,
    WechatPublishHistoryItem,
    WechatPublishHistoryResponse,
    WechatPublishRequest,
    WechatPublishResponse,
    WechatPublishStatusResponse,
)
from app.services.wechat_mp import WechatMpClient, WechatMpError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wechat"])


# ============================================================
# 发布端点
# ============================================================


@router.post(
    "/articles/{article_id}/publish-wechat",
    response_model=WechatPublishResponse,
    summary="发布文章到微信公众号",
)
async def publish_to_wechat(
    article_id: UUID,
    request: WechatPublishRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
) -> WechatPublishResponse:
    """发布文章到微信公众号。

    流程：
    1. 验证文章存在且属于当前租户
    2. 获取微信公众号配置
    3. 调用微信 API 发布
    4. 记录发布日志
    5. 如果失败，尝试降级处理
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文章不存在",
        )

    if not article.content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文章内容为空，无法发布",
        )

    # 2. 获取微信公众号配置
    stmt = select(PublishTarget).where(
        PublishTarget.id == request.config_id,
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type == PublishTargetType.WECHAT_MP,
        PublishTarget.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    wechat_config = result.scalar_one_or_none()

    if not wechat_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置微信公众号，请先在发布目标管理页面配置",
        )

    # 3. 创建发布日志（初始状态）
    publish_log = PublishLog(
        article_id=article_id,
        target_id=wechat_config.id,
        status=PublishStatus.PENDING,
        created_by=current_user.id,
    )
    db.add(publish_log)
    await db.commit()
    await db.refresh(publish_log)

    # 4. 调用微信 API 发布
    # 先解密配置。解密失败（密钥轮换/密文损坏）时给友好提示，不返回原始 CryptoError。
    try:
        wc_config = decrypt_config(wechat_config.type, wechat_config.config)
    except Exception as e:
        logger.warning("微信配置 %s 解密失败: %s", wechat_config.id, e)
        publish_log.status = PublishStatus.FAILED
        publish_log.error_message = "配置已失效（可能因密钥变更），请重新填写"
        await db.commit()
        raise HTTPException(
            status_code=400,
            detail="微信配置已失效（可能因密钥变更），请重新填写 AppSecret",
        ) from e

    try:
        client = WechatMpClient(
            db=db,
            app_id=wc_config["app_id"],
            app_secret=wc_config["app_secret"],
        )

        # 使用请求中的作者，或配置中的默认作者
        author = (
            request.author
            or wc_config.get("author", "")
            or "FNAI"
        )

        # 使用请求中的摘要，或从 seo_meta 取，或截取 content 前 120 字
        digest = request.digest
        if not digest:
            # 尝试从 seo_meta 取 description
            if article.seo_meta and isinstance(article.seo_meta, dict):
                digest = article.seo_meta.get("description", "")
        if not digest and article.content:
            # 截取 content 前 120 字（去掉 HTML 标签）
            import re
            text = re.sub(r"<[^>]+>", "", article.content)
            digest = text[:120]
        digest = digest or ""

        # 封面图：请求参数 > 配置默认 > 自动上传
        config_thumb = wechat_config.config.get("thumb_media_id", "")

        result = await client.publish_article(
            title=article.title,
            content=article.content,
            author=author,
            digest=digest,
            thumb_media_id=request.thumb_media_id,
            config_thumb_media_id=config_thumb or None,
            need_open_comment=request.need_open_comment,
            only_fans_can_comment=request.only_fans_can_comment,
        )

        # 如果自动上传了新的封面图，保存到配置中供后续复用
        new_thumb = result.get("thumb_media_id")
        if new_thumb and new_thumb != config_thumb:
            new_config = dict(wechat_config.config)
            new_config["thumb_media_id"] = new_thumb
            wechat_config.config = new_config
            await db.commit()
            logger.info(f"Auto-uploaded default thumb, saved media_id to config")

        # 更新发布日志为"已提交"（微信发布是异步的，真正成功要轮询状态）
        publish_log.status = PublishStatus.PENDING  # 等待微信审核/发布
        # 保存 publish_id 和 draft_media_id（用逗号分隔）
        publish_log.remote_id = f"{result['publish_id']},{result['draft_media_id']}"
        await db.commit()

        logger.info(
            f"Article submitted to WeChat: article_id={article_id}, "
            f"publish_id={result['publish_id']}, status=pending"
        )

        # 6. 可选：群发推送给粉丝
        mass_send_msg = None
        if request.push_to_followers:
            try:
                mass_result = await client.send_mass_message(
                    media_id=result["draft_media_id"],
                )
                mass_send_msg = f"群发成功，msg_id={mass_result.get('msg_id', '')}"
                logger.info(
                    f"Mass send triggered: article_id={article_id}, "
                    f"msg_id={mass_result.get('msg_id')}"
                )
            except WechatMpError as e:
                # 群发失败不影响发布结果，只记录日志
                mass_send_msg = f"群发失败: {e.message}"
                logger.warning(f"Mass send failed: {e.message}")

        message = "已提交发布任务，请稍后查询状态（微信审核中）"
        if mass_send_msg:
            message += f"；{mass_send_msg}"

        return WechatPublishResponse(
            success=True,
            message=message,
            publish_id=result["publish_id"],
            draft_media_id=result["draft_media_id"],
        )

    except WechatMpError as e:
        logger.error(
            f"WeChat publish failed: article_id={article_id}, "
            f"error_code={e.code}, error_message={e.message}"
        )

        # 更新发布日志为失败
        publish_log.status = PublishStatus.FAILED
        publish_log.error_message = e.message
        await db.commit()

        # 尝试降级处理
        fallback_result = await _handle_publish_fallback(
            article=article,
            error=e,
            db=db,
        )

        return fallback_result


@router.get(
    "/publish-wechat/status/{publish_id}",
    response_model=WechatPublishStatusResponse,
    summary="查询微信发布状态",
)
async def get_publish_status(
    publish_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
) -> WechatPublishStatusResponse:
    """查询微信发布状态。

    微信发布是异步的，提交后需要轮询状态。
    建议客户端每隔 2-3 秒查询一次。
    """
    tenant_id = membership.tenant_id

    # 获取微信公众号配置
    wechat_config = await _get_wechat_config(db, tenant_id)
    if not wechat_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置微信公众号",
        )

    try:
        try:
            wc_config = decrypt_config(wechat_config.type, wechat_config.config)
        except Exception as e:
            logger.warning("微信配置 %s 解密失败: %s", wechat_config.id, e)
            raise HTTPException(
                status_code=400,
                detail="微信配置已失效（可能因密钥变更），请重新填写 AppSecret",
            ) from e
        client = WechatMpClient(
            db=db,
            app_id=wc_config["app_id"],
            app_secret=wc_config["app_secret"],
        )

        status_data = await client.get_publish_status(publish_id)

        # 提取文章URL（如果发布成功）
        article_url = None
        if status_data.get("publish_status") == 0 and "article_detail" in status_data:
            items = status_data["article_detail"].get("item", [])
            if items and len(items) > 0:
                article_url = items[0].get("article_url")

        return WechatPublishStatusResponse(
            publish_id=publish_id,
            publish_status=status_data.get("publish_status", 1),
            article_id=status_data.get("article_id"),
            article_url=article_url,
            fail_reason=status_data.get("fail_reason"),
        )

    except WechatMpError as e:
        logger.error(f"Query publish status failed: {e.message}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.message,
        )


@router.get(
    "/articles/{article_id}/publish-history",
    response_model=WechatPublishHistoryResponse,
    summary="获取文章的微信发布历史",
)
async def get_publish_history(
    article_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
) -> WechatPublishHistoryResponse:
    """获取指定文章的微信发布历史。

    返回该文章所有的微信发布记录，包括：
    - 发布时间
    - 发布状态（成功/失败/处理中）
    - 文章链接（成功时）
    - 错误信息（失败时）
    """
    tenant_id = membership.tenant_id

    # 验证文章存在且属于当前租户
    stmt = select(Article).where(
        Article.id == article_id,
        Article.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="文章不存在",
        )

    # 获取微信公众号配置（只要测试号的）
    stmt = select(PublishTarget).where(
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type == PublishTargetType.WECHAT_MP,
        PublishTarget.is_active == True,  # noqa: E712
    )
    result = await db.execute(stmt)
    wechat_configs = result.scalars().all()

    if not wechat_configs:
        return WechatPublishHistoryResponse(total=0, items=[])

    # 获取测试号的配置ID
    test_config_id = None
    for config in wechat_configs:
        if config.config.get("app_id") == "wx9fd8b428a5485411":
            test_config_id = config.id
            break

    if not test_config_id:
        return WechatPublishHistoryResponse(total=0, items=[])

    # 查询发布历史
    stmt = (
        select(PublishLog)
        .where(
            PublishLog.article_id == article_id,
            PublishLog.target_id == test_config_id,
        )
        .order_by(PublishLog.published_at.desc())
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    # 获取微信客户端（用于查询article_url）
    config = None
    for c in wechat_configs:
        if c.id == test_config_id:
            config = c
            break

    # 解密配置以构建客户端。若配置缺失或解密失败（密钥轮换/密文损坏），
    # 降级为不补全 article_url，仍返回发布历史列表，避免整个接口 500。
    client = None
    if config is not None:
        try:
            wc_config = decrypt_config(config.type, config.config)
            client = WechatMpClient(
                db=db,
                app_id=wc_config["app_id"],
                app_secret=wc_config["app_secret"],
            )
        except Exception as e:
            logger.warning(
                "微信配置 %s 解密失败，发布历史将不补全文章链接: %s",
                test_config_id, e,
            )

    # 构建响应
    items = []
    for log in logs:
        # 解析 publish_id（从 remote_id 中提取）
        publish_id = None
        if log.remote_id:
            parts = log.remote_id.split(",", 1)
            publish_id = parts[0]

        # 如果状态是成功，尝试获取文章链接（client 为 None 时跳过）
        article_url = None
        if client is not None and log.status == PublishStatus.SUCCESS and publish_id:
            try:
                status_data = await client.get_publish_status(publish_id)
                if status_data.get("publish_status") == 0 and "article_detail" in status_data:
                    items_data = status_data["article_detail"].get("item", [])
                    if items_data and len(items_data) > 0:
                        article_url = items_data[0].get("article_url")
            except Exception as e:
                logger.warning(f"Failed to get article_url for publish_id={publish_id}: {e}")

        items.append(
            WechatPublishHistoryItem(
                id=log.id,
                publish_id=publish_id,
                status=log.status.value,
                published_at=log.published_at.isoformat(),
                error_message=log.error_message,
                article_url=article_url,
            )
        )

    return WechatPublishHistoryResponse(
        total=len(items),
        items=items,
    )


@router.post(
    "/mass-send",
    response_model=WechatMassSendResponse,
    summary="群发图文消息给所有粉丝",
)
async def mass_send_message(
    request: WechatMassSendRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
) -> WechatMassSendResponse:
    """群发已发布的图文消息给所有粉丝。

    注意事项：
    1. 需要先调用发布接口获取 publish_id
    2. 群发使用的是草稿 media_id（已自动从数据库获取）
    3. 测试号每天只能群发1次，认证公众号每月4次
    4. 群发后粉丝会立即收到推送消息
    """
    tenant_id = membership.tenant_id

    # 获取微信公众号配置
    wechat_config = await _get_wechat_config(db, tenant_id)
    if not wechat_config:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="未配置微信公众号",
        )

    # 从数据库中查找 publish_log，获取 draft_media_id
    # remote_id 格式: "publish_id,draft_media_id"
    stmt = select(PublishLog).where(
        PublishLog.target_id == wechat_config.id,
    )
    result = await db.execute(stmt)
    all_logs = result.scalars().all()

    # 查找匹配的publish_log（remote_id以publish_id开头）
    publish_log = None
    for log in all_logs:
        if log.remote_id and log.remote_id.startswith(f"{request.publish_id},"):
            publish_log = log
            break

    if not publish_log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"未找到发布记录: {request.publish_id}",
        )

    if publish_log.status != PublishStatus.SUCCESS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"文章尚未发布成功，当前状态: {publish_log.status}",
        )

    # 解析 draft_media_id
    parts = publish_log.remote_id.split(",", 1)
    if len(parts) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="发布记录中未找到 draft_media_id，请重新发布文章",
        )

    draft_media_id = parts[1]

    try:
        try:
            wc_config = decrypt_config(wechat_config.type, wechat_config.config)
        except Exception as e:
            logger.warning("微信配置 %s 解密失败: %s", wechat_config.id, e)
            raise HTTPException(
                status_code=400,
                detail="微信配置已失效（可能因密钥变更），请重新填写 AppSecret",
            ) from e
        client = WechatMpClient(
            db=db,
            app_id=wc_config["app_id"],
            app_secret=wc_config["app_secret"],
        )

        # 执行群发
        mass_result = await client.send_mass_message(
            media_id=draft_media_id,
            send_ignore_reprint=request.send_ignore_reprint,
        )

        logger.info(
            f"Mass send success: tenant={tenant_id}, "
            f"publish_id={request.publish_id}, msg_id={mass_result.get('msg_id')}"
        )

        return WechatMassSendResponse(
            success=True,
            message="群发成功，粉丝即将收到推送消息",
            msg_id=str(mass_result.get("msg_id")),
            msg_data_id=str(mass_result.get("msg_data_id")),
        )

    except WechatMpError as e:
        logger.error(f"Mass send failed: {e.message}")
        return WechatMassSendResponse(
            success=False,
            message=f"群发失败: {e.message}",
        )


# ============================================================
# 配置管理端点
# ============================================================


@router.post(
    "/wechat-configs",
    response_model=WechatConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建微信公众号配置",
)
async def create_wechat_config(
    request: WechatConfigCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
) -> WechatConfigResponse:
    """创建微信公众号配置。

    一个租户可以配置多个微信公众号。
    """
    tenant_id = membership.tenant_id

    # 检查 app_id 是否已存在（同一租户下 app_id 不能重复）
    stmt = select(PublishTarget).where(
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type == PublishTargetType.WECHAT_MP,
    )
    result = await db.execute(stmt)
    existing_configs = result.scalars().all()

    for config in existing_configs:
        if config.config.get("app_id") == request.app_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"该 App ID ({request.app_id}) 已存在配置",
            )

    # 创建配置（加密 app_secret 后存储）
    config = PublishTarget(
        tenant_id=tenant_id,
        name=request.name,
        type=PublishTargetType.WECHAT_MP,  # 微信公众号专用类型
        config=encrypt_config(
            PublishTargetType.WECHAT_MP,
            {
                "app_id": request.app_id,
                "app_secret": request.app_secret,
                "author": request.author or "",
                "thumb_media_id": request.thumb_media_id or "",
                "platform": "wechat_mp",  # 保留标识，向后兼容
            },
        ),
        is_active=True,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)

    return WechatConfigResponse(
        id=config.id,
        name=config.name,
        app_id=request.app_id,
        author=request.author,
        is_active=config.is_active,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


@router.get(
    "/wechat-configs",
    response_model=list[WechatConfigResponse],
    summary="列出微信公众号配置",
)
async def list_wechat_configs(
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
) -> list[WechatConfigResponse]:
    """列出当前租户的微信公众号配置。"""
    tenant_id = membership.tenant_id

    stmt = select(PublishTarget).where(
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type == PublishTargetType.WECHAT_MP,
    )
    result = await db.execute(stmt)
    configs = list(result.scalars().all())

    return [
        WechatConfigResponse(
            id=c.id,
            name=c.name,
            app_id=c.config.get("app_id", ""),
            author=c.config.get("author"),
            is_active=c.is_active,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in configs
    ]


@router.put(
    "/wechat-configs/{config_id}",
    response_model=WechatConfigResponse,
    summary="更新微信公众号配置",
)
async def update_wechat_config(
    config_id: UUID,
    request: WechatConfigUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
) -> WechatConfigResponse:
    """更新微信公众号配置。"""
    tenant_id = membership.tenant_id

    stmt = select(PublishTarget).where(
        PublishTarget.id == config_id,
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type == PublishTargetType.WECHAT_MP,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="微信公众号配置不存在",
        )

    # 更新字段
    # ⚠️ JSONB 需要构造新 dict 再整体赋值，否则原地修改 SQLAlchemy 检测不到，不会落库
    if request.name is not None:
        config.name = request.name

    new_config = dict(config.config)  # 复制一份，避免原地修改
    config_changed = False
    if request.app_secret is not None:
        new_config["app_secret"] = request.app_secret  # 明文，稍后统一加密
        config_changed = True
    if request.author is not None:
        new_config["author"] = request.author
        config_changed = True
    if request.thumb_media_id is not None:
        new_config["thumb_media_id"] = request.thumb_media_id
        config_changed = True
    if config_changed:
        # 加密敏感字段后整体赋值（encrypt_config 幂等，未变更的已加密值不会重复加密）
        config.config = encrypt_config(config.type, new_config)

    await db.commit()
    await db.refresh(config)

    return WechatConfigResponse(
        id=config.id,
        name=config.name,
        app_id=config.config.get("app_id", ""),
        author=config.config.get("author"),
        is_active=config.is_active,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


@router.delete(
    "/wechat-configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除微信公众号配置",
)
async def delete_wechat_config(
    config_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
) -> None:
    """删除微信公众号配置。"""
    tenant_id = membership.tenant_id

    stmt = select(PublishTarget).where(
        PublishTarget.id == config_id,
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.type == PublishTargetType.WECHAT_MP,
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="微信公众号配置不存在",
        )

    await db.delete(config)
    await db.commit()


# ============================================================
# 内部辅助函数
# ============================================================


async def _get_wechat_config(
    db: AsyncSession, tenant_id: UUID
) -> PublishTarget | None:
    """获取微信公众号配置。"""
    stmt = select(PublishTarget).where(
        PublishTarget.tenant_id == tenant_id,
        PublishTarget.is_active == True,  # noqa: E712
        PublishTarget.type == PublishTargetType.WECHAT_MP,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _handle_publish_fallback(
    article: Article,
    error: WechatMpError,
    db: AsyncSession,
) -> WechatPublishResponse:
    """处理发布失败的降级逻辑。"""

    # 1. 内容违规 — 不降级，直接返回错误
    if error.wx_errcode == 45010:
        return WechatPublishResponse(
            success=False,
            message=f"文章内容不符合微信公众号规范: {error.message}",
            fallback=False,
        )

    # 2. Token 失效 — 提示重新配置
    if error.wx_errcode in (40001, 40002, 40013):
        return WechatPublishResponse(
            success=False,
            message="微信公众号配置无效，请检查 AppID 和 AppSecret",
            fallback=False,
        )

    # 3. 配额超限 — 提示稍后重试
    if error.wx_errcode == 45009:
        return WechatPublishResponse(
            success=False,
            message="微信公众号调用频率超限，请稍后重试",
            fallback=True,
            fallback_strategy="queue_retry",
        )

    # 4. 其他错误 — 降级为手动复制
    formatted_content = _format_for_wechat(article)

    return WechatPublishResponse(
        success=False,
        message=f"自动发布失败: {error.message}",
        fallback=True,
        fallback_strategy="manual_copy",
        copy_content=formatted_content,
    )


def _format_for_wechat(article: Article) -> str:
    """格式化内容为微信公众号可复制格式。"""
    # 获取摘要（从 seo_meta 或截取 content）
    summary = "无"
    if article.seo_meta and isinstance(article.seo_meta, dict):
        summary = article.seo_meta.get("description", "无")

    content = f"""【标题】{article.title}

【摘要】{summary}

【正文】
{article.content}

---
以上内容由 FNAI 自动生成，请复制到微信公众号后台发布。
"""
    return content
