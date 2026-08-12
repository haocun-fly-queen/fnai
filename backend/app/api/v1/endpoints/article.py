"""Article HTTP 端点（阶段 4 Step 2）。

7 个端点（Step 2 范围）：

    GET    /articles                 列文章（任何成员）
    POST   /articles                 创建文章（MEMBER+）
    GET    /articles/{id}            文章详情（任何成员）
    PATCH  /articles/{id}            编辑保存（MEMBER+）
    DELETE /articles/{id}            删除（MEMBER+）

    POST   /articles/{id}/versions   打版本快照（MEMBER+）
    GET    /articles/{id}/versions   列版本（任何成员）

    GET    /templates                列可用模板（任何成员）

Step 3 之后还会加：
    POST   /articles/{id}/generate   触发生成 pipeline（MEMBER+）
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.membership import Role, TenantMember
from app.models.user import User
from app.schemas.article import (
    ArticleCreate,
    ArticleListResponse,
    ArticleRead,
    ArticleSummary,
    ArticleUpdate,
    BatchGenerateRequest,
    BatchGenerateResponse,
    GenerationRequest,
    TemplateListResponse,
    TemplateSummary,
    VersionCreate,
    VersionListResponse,
    VersionRead,
)
from app.services import article as article_service
from app.services import generation as generation_service
from app.services.article import ArticleError
from app.services.generation import GenerationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["articles"])


# ============================================================
# 业务异常 → HTTP
# ============================================================


def _to_http(err: ArticleError) -> HTTPException:
    code = err.code
    if code in ("not_found", "template_not_found"):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": code, "message": err.message},
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": err.message},
    )


# ============================================================
# /articles
# ============================================================


@router.get("/articles", response_model=ArticleListResponse, summary="列文章（任何成员）")
async def list_articles_endpoint(
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArticleListResponse:
    items, total = await article_service.list_articles(db, tenant_id=membership.tenant_id)
    return ArticleListResponse(
        items=[ArticleSummary.model_validate(a) for a in items],
        total=total,
    )


@router.post(
    "/articles",
    response_model=ArticleRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建文章（MEMBER+）",
)
async def create_article_endpoint(
    payload: ArticleCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArticleRead:
    try:
        article = await article_service.create_article(
            db,
            tenant_id=membership.tenant_id,
            user_id=current_user.id,
            title=payload.title,
            topic=payload.topic,
            template_code=payload.template_code,
            knowledge_base_id=payload.knowledge_base_id,
            content=payload.content,
            source_document_ids=payload.source_document_ids,
            scheduled_at=payload.scheduled_at,
        )
    except ArticleError as exc:
        raise _to_http(exc) from exc
    return ArticleRead.model_validate(article)


@router.get(
    "/articles/{article_id}",
    response_model=ArticleRead,
    summary="文章详情（任何成员）",
)
async def get_article_endpoint(
    article_id: UUID,
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArticleRead:
    try:
        article = await article_service.get_article(
            db, tenant_id=membership.tenant_id, article_id=article_id,
        )
    except ArticleError as exc:
        raise _to_http(exc) from exc
    return ArticleRead.model_validate(article)


@router.patch(
    "/articles/{article_id}",
    response_model=ArticleRead,
    summary="编辑保存（MEMBER+）",
)
async def update_article_endpoint(
    article_id: UUID,
    payload: ArticleUpdate,
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArticleRead:
    try:
        article = await article_service.update_article(
            db,
            tenant_id=membership.tenant_id,
            article_id=article_id,
            title=payload.title,
            content=payload.content,
            seo_meta=payload.seo_meta,
        )
    except ArticleError as exc:
        raise _to_http(exc) from exc
    return ArticleRead.model_validate(article)


@router.delete(
    "/articles/{article_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除文章（MEMBER+）",
)
async def delete_article_endpoint(
    article_id: UUID,
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    try:
        await article_service.delete_article(
            db, tenant_id=membership.tenant_id, article_id=article_id,
        )
    except ArticleError as exc:
        raise _to_http(exc) from exc


# ============================================================
# /articles/{id}/versions
# ============================================================


@router.post(
    "/articles/{article_id}/versions",
    response_model=VersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="打版本快照（MEMBER+）",
)
async def save_version_endpoint(
    article_id: UUID,
    payload: VersionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VersionRead:
    try:
        version = await article_service.save_version(
            db,
            tenant_id=membership.tenant_id,
            article_id=article_id,
            user_id=current_user.id,
            note=payload.note,
        )
    except ArticleError as exc:
        raise _to_http(exc) from exc
    return VersionRead.model_validate(version)


@router.get(
    "/articles/{article_id}/versions",
    response_model=VersionListResponse,
    summary="列版本历史（任何成员）",
)
async def list_versions_endpoint(
    article_id: UUID,
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> VersionListResponse:
    try:
        items, total = await article_service.list_versions(
            db, tenant_id=membership.tenant_id, article_id=article_id,
        )
    except ArticleError as exc:
        raise _to_http(exc) from exc
    return VersionListResponse(
        items=[VersionRead.model_validate(v) for v in items],
        total=total,
    )


# ============================================================
# /templates
# ============================================================


@router.get("/templates", response_model=TemplateListResponse, summary="列可用模板（任何成员）")
async def list_templates_endpoint(
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TemplateListResponse:
    items, total = await article_service.list_templates(db, tenant_id=membership.tenant_id)
    return TemplateListResponse(
        items=[TemplateSummary.model_validate(t) for t in items],
        total=total,
    )


# ============================================================
# /articles/{id}/generate （Step 4：同步生成）
# ============================================================


@router.post(
    "/articles/{article_id}/generate",
    response_model=ArticleRead,
    summary="触发四阶段生成 pipeline（MEMBER+，同步返回，30-90秒）",
)
async def generate_article_endpoint(
    article_id: UUID,
    payload: GenerationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArticleRead:
    """POST /api/v1/articles/{article_id}/generate

    在指定文章上跑完整四阶段生成（outline → section → seo → quality）。
    同步返回——客户端要等 30-90 秒。流式版本留给 V1.5。

    返回：更新后的 article（status=completed / failed，content/outline/seo_meta 已填）
    """
    # 1) 取文章（校验存在 + 租户归属）
    try:
        article = await article_service.get_article(
            db, tenant_id=membership.tenant_id, article_id=article_id,
        )
    except ArticleError as exc:
        raise _to_http(exc) from exc

    # 2) 跑生成 pipeline
    try:
        article = await generation_service.generate_article(
            db,
            tenant_id=membership.tenant_id,
            user_id=current_user.id,
            article=article,
            target_word_count=payload.target_word_count,
        )
    except GenerationError as exc:
        # 模板不存在等 pipeline 启动前的错（pipeline 内部错会写 FAILED 不抛）
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return ArticleRead.model_validate(article)


# ============================================================
# 批量生成（Phase 2）
# ============================================================


@router.post(
    "/articles/batch-generate",
    response_model=BatchGenerateResponse,
    summary="批量生成文章（1-20 篇）",
)
async def batch_generate_endpoint(
    payload: BatchGenerateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BatchGenerateResponse:
    """POST /api/v1/articles/batch-generate

    一次提交多篇文章的生成任务。同步创建 Article 记录，异步投递 Celery 任务。
    前端轮询 GET /articles/{id} 查看各篇 status。
    """
    from app.workers.tasks import generate_article_task

    article_ids: list[UUID] = []

    for item in payload.items:
        try:
            article = await article_service.create_article(
                db,
                tenant_id=membership.tenant_id,
                user_id=current_user.id,
                title=item.title,
                topic=item.topic,
                template_code=item.template_code,
                knowledge_base_id=item.knowledge_base_id,
                content="",
                source_document_ids=item.source_document_ids,
            )
        except ArticleError as exc:
            raise _to_http(exc) from exc

        article_ids.append(article.id)

        # 投递 Celery 异步生成任务
        generate_article_task.delay(
            str(article.id),
            str(current_user.id),
        )

    logger.info(
        "Batch generate: tenant=%s count=%d articles=%s",
        membership.tenant_id, len(article_ids), article_ids,
    )

    return BatchGenerateResponse(
        article_ids=article_ids,
        message=f"已提交 {len(article_ids)} 篇文章的生成任务",
    )
