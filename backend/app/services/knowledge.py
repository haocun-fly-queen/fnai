"""KnowledgeBase + Document 业务逻辑。

⚠️ Step 2 实现（2026-06-25）：
    - KB 增删改查
    - Document 上传（落盘 + 写 DB，status=PENDING）
    - Document 列表/详情/删除（同步删文件）
    - 异步处理（Celery 解析/embedding）Step 3 再加

给 Java 同事的提示：
- Python service 用"模块级函数"而不是 class，因为无状态
- 所有函数都接 db: AsyncSession 参数（FastAPI Depends 注入）
- 业务校验失败 → raise KnowledgeError(code, message) → 端点 catch → 4xx 响应
"""

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import logger
from app.models import (
    Document,
    DocumentChunk,
    DocumentStatus,
    KnowledgeBase,
    TenantMember,
)
from app.models.membership import Role
from app.services import storage

# ============================================================
# 业务异常
# ============================================================


class KnowledgeError(Exception):
    """知识库业务异常。端点层翻译成 4xx。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# ============================================================
# 1️⃣ KnowledgeBase CRUD
# ============================================================


async def create_kb(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    name: str,
    slug: str,
    description: str | None = None,
) -> KnowledgeBase:
    """创建知识库。

    Args:
        tenant_id: 所属租户（从 token 取）
        user_id: 创建者（从 token 取）
        name: 知识库名字
        slug: URL 友好标识
        description: 描述（可选）

    Returns:
        新创建的 KnowledgeBase 实例

    Raises:
        KnowledgeError(code="slug_taken"): slug 在该租户下已存在
    """
    kb = KnowledgeBase(
        tenant_id=tenant_id,
        name=name,
        slug=slug,
        description=description,
        created_by=user_id,
    )
    db.add(kb)
    try:
        await db.commit()
    except IntegrityError:
        # 触发 unique constraint uq_knowledge_bases_tenant_slug
        await db.rollback()
        raise KnowledgeError(
            code="slug_taken",
            message=f"slug '{slug}' 在该租户下已被使用",
        )
    await db.refresh(kb)
    logger.info("KB created: tenant=%s slug=%s id=%s", tenant_id, slug, kb.id)
    return kb


async def list_kbs(
    db: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[list[KnowledgeBase], int]:
    """列出当前租户的所有 KB（含每个 KB 的文档数）。

    Returns:
        (kb_list, total_count)
    """
    # 一次 SQL 拿全：KB 基础信息 + 各 KB 的文档数
    # 用子查询 LEFT JOIN documents
    stmt = (
        select(
            KnowledgeBase,
            func.count(Document.id).label("document_count"),
        )
        .where(KnowledgeBase.tenant_id == tenant_id)
        .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
        .group_by(KnowledgeBase.id)
        .order_by(KnowledgeBase.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()
    kbs: list[KnowledgeBase] = []
    for kb, doc_count in rows:
        # 把 document_count 挂到 ORM 对象上（这样 schema 序列化能读到）
        kb.document_count = doc_count  # type: ignore[attr-defined]
        kbs.append(kb)
    return kbs, len(kbs)


async def get_kb(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    kb_id: UUID,
) -> KnowledgeBase:
    """取单个 KB（按租户过滤）。

    Raises:
        KnowledgeError(code="not_found"): 不存在或不属于该租户
    """
    stmt = select(KnowledgeBase).where(
        KnowledgeBase.id == kb_id,
        KnowledgeBase.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    kb = result.scalar_one_or_none()
    if kb is None:
        raise KnowledgeError(
            code="not_found",
            message="知识库不存在或不属于当前租户",
        )
    return kb


async def delete_kb(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    kb_id: UUID,
) -> None:
    """删除 KB（CASCADE 自动删 documents + chunks）。

    副作用：
        - DB 端：删 KB → CASCADE 删 documents → CASCADE 删 chunks
        - 文件端：清空 /tmp/fnai-storage/tenants/{tid}/kb/{kid}/

    Raises:
        KnowledgeError(code="not_found"): 不存在
    """
    # 1) 先确认存在
    await get_kb(db, tenant_id=tenant_id, kb_id=kb_id)

    # 2) 删 DB（先收集要删的 storage_key，因为 CASCADE 之后查不到了）
    #    ⚠️ 用 session.execute(sa_delete) 走 CASCADE
    stmt = select(Document.storage_key).where(
        Document.knowledge_base_id == kb_id,
    )
    result = await db.execute(stmt)
    storage_keys = [row[0] for row in result.all()]

    # 删 KB（CASCADE 删 documents + chunks）
    await db.execute(
        sa_delete(KnowledgeBase).where(KnowledgeBase.id == kb_id)
    )
    await db.commit()

    # 3) 删文件（不阻塞 commit，失败了记日志）
    deleted = 0
    for key in storage_keys:
        if storage.delete(key):
            deleted += 1
    # 顺便清空 KB 目录
    prefix = f"tenants/{tenant_id}/kb/{kb_id}"
    try:
        storage.delete_prefix(prefix + "/")
    except (OSError, ValueError) as exc:
        logger.warning("delete_prefix %s failed: %s", prefix, exc)

    logger.info(
        "KB deleted: id=%s files_deleted=%d", kb_id, deleted,
    )


# ============================================================
# 2️⃣ Document 上传 / 列表 / 详情 / 删除
# ============================================================


async def upload_document(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    kb_id: UUID,
    uploaded_by: UUID,
    filename: str,
    content_type: str,
    data: bytes,
) -> Document:
    """上传文档（落盘 + 写 DB，status=PENDING）。

    ⚠️ 还没接 Celery 异步处理，文档会卡在 PENDING 状态
    Step 3 会加 process_document.delay(doc_id) 触发处理

    Args:
        db: 异步 session
        tenant_id: 租户 ID（从 token 取）
        kb_id: 目标 KB ID
        uploaded_by: 上传者用户 ID
        filename: 原始文件名
        content_type: MIME type
        data: 文件字节

    Returns:
        新建的 Document 实例

    Raises:
        KnowledgeError(code="kb_not_found"): KB 不存在
        KnowledgeError(code="mime_not_allowed"): MIME 不在白名单
        KnowledgeError(code="file_too_large"): 超过 max_upload_size
    """
    # 1) 校验 KB 存在
    await get_kb(db, tenant_id=tenant_id, kb_id=kb_id)

    # 2) 校验 MIME 白名单
    if content_type not in settings.allowed_mime_types:
        raise KnowledgeError(
            code="mime_not_allowed",
            message=(
                f"不支持的文件类型: {content_type}。"
                f"允许: {', '.join(settings.allowed_mime_types)}"
            ),
        )

    # 3) 校验文件大小
    if len(data) > settings.max_upload_size_bytes:
        mb = settings.max_upload_size_bytes / (1024 * 1024)
        raise KnowledgeError(
            code="file_too_large",
            message=f"文件过大（{len(data)} 字节），上限 {mb:.0f}MB",
        )

    # 4) 生成 doc_id + storage_key，先写 DB 占位（status=PENDING）
    doc_id = uuid4()
    storage_key = storage.build_storage_key(
        tenant_id=tenant_id,
        knowledge_base_id=kb_id,
        document_id=doc_id,
        filename=filename,
    )

    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        knowledge_base_id=kb_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        storage_key=storage_key,
        status=DocumentStatus.PENDING,
        chunk_count=0,
        uploaded_by=uploaded_by,
    )
    db.add(doc)
    await db.commit()

    # 5) 落盘（DB 写完再写文件，避免写了一半不一致）
    try:
        storage.put_bytes(storage_key, data)
    except OSError as exc:
        # 文件写失败 → 回滚 DB + 把状态改成 FAILED
        # 但这条 doc 行保留（前端能看到"上传失败"）
        doc.status = DocumentStatus.FAILED
        doc.error_message = f"文件写入失败: {exc}"
        await db.commit()
        raise KnowledgeError(
            code="storage_write_failed",
            message=f"文件写入失败: {exc}",
        )

    logger.info(
        "Document uploaded: id=%s kb=%s size=%d filename=%s",
        doc_id, kb_id, len(data), filename,
    )
    return doc


async def list_documents(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    kb_id: UUID,
) -> tuple[list[Document], int, dict[str, int]]:
    """列 KB 下的所有文档（含按状态统计）。

    Returns:
        (docs, total, status_counts)
        status_counts: {"pending": 3, "ready": 10, "failed": 1}
    """
    # 1) 校验 KB
    await get_kb(db, tenant_id=tenant_id, kb_id=kb_id)

    # 2) 取所有文档
    stmt = (
        select(Document)
        .where(
            Document.knowledge_base_id == kb_id,
            Document.tenant_id == tenant_id,
        )
        .order_by(Document.created_at.desc())
    )
    result = await db.execute(stmt)
    docs = list(result.scalars().all())

    # 3) 按状态统计
    counts: dict[str, int] = {"pending": 0, "ready": 0, "failed": 0}
    for d in docs:
        s = d.status.value
        if s in ("pending", "processing"):
            counts["pending"] += 1
        elif s == "ready":
            counts["ready"] += 1
        elif s == "failed":
            counts["failed"] += 1

    return docs, len(docs), counts


async def get_document(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    kb_id: UUID,
    doc_id: UUID,
) -> Document:
    """取单个文档（按 KB + 租户过滤）。

    Raises:
        KnowledgeError(code="not_found")
    """
    stmt = select(Document).where(
        Document.id == doc_id,
        Document.knowledge_base_id == kb_id,
        Document.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()
    if doc is None:
        raise KnowledgeError(
            code="not_found",
            message="文档不存在或不属于该知识库",
        )
    return doc


async def delete_document(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    kb_id: UUID,
    doc_id: UUID,
) -> None:
    """删除文档（CASCADE 删 chunks + 文件）。

    Raises:
        KnowledgeError(code="not_found")
    """
    # 1) 拿 doc（顺便校验存在 + 租户归属）
    doc = await get_document(
        db, tenant_id=tenant_id, kb_id=kb_id, doc_id=doc_id,
    )
    storage_key = doc.storage_key

    # 2) 删 DB（CASCADE 删 chunks）
    await db.execute(sa_delete(Document).where(Document.id == doc_id))
    await db.commit()

    # 3) 删文件
    storage.delete(storage_key)
    logger.info("Document deleted: id=%s", doc_id)
