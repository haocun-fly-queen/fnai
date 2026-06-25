"""Knowledge base HTTP 端点（Step 2 实现，2026-06-25）。

8 个端点：

    POST   /knowledge                          创建 KB（MEMBER+）
    GET    /knowledge                          列 KB（任何成员）
    GET    /knowledge/{kb_id}                  KB 详情（任何成员）
    DELETE /knowledge/{kb_id}                  删 KB（ADMIN+）

    POST   /knowledge/{kb_id}/documents        上传文档（MEMBER+）
    GET    /knowledge/{kb_id}/documents        列文档（任何成员）
    GET    /knowledge/{kb_id}/documents/{id}   文档详情（任何成员）
    DELETE /knowledge/{kb_id}/documents/{id}   删文档（MEMBER+）

⚠️ 设计：
- 端点"瘦"：接参 → 调 service → 翻译 KnowledgeError → HTTPException
- 鉴权用 Depends(require_role(Role.X))
- 上传用 multipart/form-data，FastAPI 自动解析
"""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, require_role
from app.db.session import get_db
from app.models.membership import Role, TenantMember
from app.models.user import User
from app.schemas.knowledge import (
    DocumentListResponse,
    DocumentRead,
    KnowledgeBaseCreate,
    KnowledgeBaseListResponse,
    KnowledgeBaseRead,
)
from app.services import knowledge as knowledge_service
from app.services.knowledge import KnowledgeError

logger = logging.getLogger(__name__)

# ============================================================
# 路由配置
# ============================================================
# prefix="/knowledge" → /api/v1/knowledge/...
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ============================================================
# 工具：业务异常 → HTTP 异常
# ============================================================


def _knowledge_error_to_http(err: KnowledgeError) -> HTTPException:
    """把 KnowledgeError 翻译成合适的 HTTP 状态码。"""
    code = err.code

    # 404 资源不存在
    if code in ("not_found", "kb_not_found"):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": code, "message": err.message},
        )

    # 409 状态冲突（slug 已存在）
    if code == "slug_taken":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": code, "message": err.message},
        )

    # 413 Payload Too Large
    if code == "file_too_large":
        return HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": code, "message": err.message},
        )

    # 415 Unsupported Media Type
    if code == "mime_not_allowed":
        return HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"code": code, "message": err.message},
        )

    # 500 兜底
    if code == "storage_write_failed":
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": code, "message": err.message},
        )

    # 400 兜底
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"code": code, "message": err.message},
    )


# ============================================================
# KnowledgeBase 端点
# ============================================================


@router.post(
    "",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
    summary="创建知识库（MEMBER+）",
)
async def create_kb(
    payload: KnowledgeBaseCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeBaseRead:
    """POST /api/v1/knowledge

    创建一个新知识库。
    权限：MEMBER 及以上（任何成员都能建 KB）
    """
    try:
        kb = await knowledge_service.create_kb(
            db,
            tenant_id=membership.tenant_id,
            user_id=current_user.id,
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
        )
    except KnowledgeError as exc:
        raise _knowledge_error_to_http(exc) from exc

    # document_count 默认 0（新建的 KB 还没文档）
    kb.document_count = 0  # type: ignore[attr-defined]
    return KnowledgeBaseRead.model_validate(kb)


@router.get(
    "",
    response_model=KnowledgeBaseListResponse,
    summary="列出当前租户的所有知识库（任何成员）",
)
async def list_kbs(
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeBaseListResponse:
    """GET /api/v1/knowledge

    列出当前租户的所有 KB，含每个 KB 的文档数。
    权限：任何成员（VIEWER 也能看列表）
    """
    kbs, total = await knowledge_service.list_kbs(
        db, tenant_id=membership.tenant_id,
    )
    return KnowledgeBaseListResponse(
        items=[KnowledgeBaseRead.model_validate(kb) for kb in kbs],
        total=total,
    )


@router.get(
    "/{kb_id}",
    response_model=KnowledgeBaseRead,
    summary="知识库详情（任何成员）",
)
async def get_kb(
    kb_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> KnowledgeBaseRead:
    """GET /api/v1/knowledge/{kb_id}"""
    try:
        kb = await knowledge_service.get_kb(
            db, tenant_id=membership.tenant_id, kb_id=kb_id,
        )
    except KnowledgeError as exc:
        raise _knowledge_error_to_http(exc) from exc

    # 取 document_count
    from sqlalchemy import func, select
    from app.models import Document

    count = await db.scalar(
        select(func.count(Document.id)).where(
            Document.knowledge_base_id == kb_id,
        )
    )
    kb.document_count = count or 0  # type: ignore[attr-defined]
    return KnowledgeBaseRead.model_validate(kb)


@router.delete(
    "/{kb_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除知识库（ADMIN+，CASCADE 删文档）",
)
async def delete_kb(
    kb_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """DELETE /api/v1/knowledge/{kb_id}

    删除 KB + 所有文档 + chunks + MinIO 对象。
    权限：ADMIN 及以上（不能由 MEMBER 误删）
    """
    try:
        await knowledge_service.delete_kb(
            db, tenant_id=membership.tenant_id, kb_id=kb_id,
        )
    except KnowledgeError as exc:
        raise _knowledge_error_to_http(exc) from exc


# ============================================================
# Document 端点
# ============================================================


@router.post(
    "/{kb_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="上传文档到知识库（MEMBER+）",
)
async def upload_document(
    kb_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    # FastAPI 自动从 multipart/form-data 拿 file 字段
    # File(...) 表示必填
    file: Annotated[UploadFile, File(description="要上传的文件（pdf/docx/pptx/txt/md）")],
) -> DocumentRead:
    """POST /api/v1/knowledge/{kb_id}/documents

    上传一个文件到知识库。
    - 文件大小 ≤ 200MB（settings.max_upload_size_bytes）
    - MIME 必须在白名单
    - 同步落盘到 /tmp/fnai-storage/（Step 4 切 MinIO）
    - 异步解析/embedding（Step 3 接入 Celery）

    权限：MEMBER 及以上
    """
    # ⚠️ 必读 await：UploadFile.read() 是 async
    data = await file.read()

    try:
        doc = await knowledge_service.upload_document(
            db,
            tenant_id=membership.tenant_id,
            kb_id=kb_id,
            uploaded_by=current_user.id,
            filename=file.filename or "untitled",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        )
    except KnowledgeError as exc:
        raise _knowledge_error_to_http(exc) from exc

    return DocumentRead.model_validate(doc)


@router.get(
    "/{kb_id}/documents",
    response_model=DocumentListResponse,
    summary="列出知识库的所有文档（任何成员）",
)
async def list_documents(
    kb_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentListResponse:
    """GET /api/v1/knowledge/{kb_id}/documents

    列出 KB 下所有文档，含按状态统计。
    """
    try:
        docs, total, counts = await knowledge_service.list_documents(
            db, tenant_id=membership.tenant_id, kb_id=kb_id,
        )
    except KnowledgeError as exc:
        raise _knowledge_error_to_http(exc) from exc

    return DocumentListResponse(
        items=[DocumentRead.model_validate(d) for d in docs],
        total=total,
        pending_count=counts["pending"],
        ready_count=counts["ready"],
        failed_count=counts["failed"],
    )


@router.get(
    "/{kb_id}/documents/{doc_id}",
    response_model=DocumentRead,
    summary="文档详情（任何成员）",
)
async def get_document(
    kb_id: UUID,
    doc_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.VIEWER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentRead:
    """GET /api/v1/knowledge/{kb_id}/documents/{doc_id}"""
    try:
        doc = await knowledge_service.get_document(
            db,
            tenant_id=membership.tenant_id,
            kb_id=kb_id,
            doc_id=doc_id,
        )
    except KnowledgeError as exc:
        raise _knowledge_error_to_http(exc) from exc
    return DocumentRead.model_validate(doc)


@router.delete(
    "/{kb_id}/documents/{doc_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除文档（MEMBER+，CASCADE 删 chunks + 文件）",
)
async def delete_document(
    kb_id: UUID,
    doc_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    membership: Annotated[TenantMember, Depends(require_role(Role.MEMBER))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """DELETE /api/v1/knowledge/{kb_id}/documents/{doc_id}"""
    try:
        await knowledge_service.delete_document(
            db,
            tenant_id=membership.tenant_id,
            kb_id=kb_id,
            doc_id=doc_id,
        )
    except KnowledgeError as exc:
        raise _knowledge_error_to_http(exc) from exc
