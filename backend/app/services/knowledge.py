"""KnowledgeBase + Document 业务逻辑。

⚠️ Step 2 实现（2026-06-25）：
    - KB 增删改查
    - Document 上传（落盘 + 写 DB，status=PENDING）
    - Document 列表/详情/删除（同步删文件）

✅ Step 3 实现（2026-06-26）：
    - 上传完成后 process_document.delay(doc_id) 触发 Celery 异步处理
      （解析 → 切分 → embedding → 写 chunks → status=READY/FAILED）

给 Java 同事的提示：
- Python service 用"模块级函数"而不是 class，因为无状态
- 所有函数都接 db: AsyncSession 参数（FastAPI Depends 注入）
- 业务校验失败 → raise KnowledgeError(code, message) → 端点 catch → 4xx 响应
"""

from typing import Any
from uuid import UUID, uuid4

import asyncio

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

    ✅ Step 3：落盘成功后 process_document.delay(doc_id) 触发异步处理，
       文档状态会由 worker 推进 PENDING → PROCESSING → READY/FAILED。

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

    # 6) 触发 Celery 异步处理（解析 → 切分 → embedding → 写 chunks）
    #    ⚠️ 用 .delay() 投递到队列后立即返回，不阻塞 HTTP 响应。
    #    worker 没起时任务会堆在 Redis 队列里，等 worker 起来再消费（不会丢）。
    #    投递失败（如 Redis 挂了）不影响上传本身——文档已落盘，可重新触发。
    try:
        # 延迟 import：避免 FastAPI 启动时强依赖 celery 配置
        from app.workers.tasks import process_document

        process_document.delay(str(doc_id))
    except Exception as exc:
        # 投递失败只记日志，不让上传失败（文档已在 DB+磁盘，可后续重处理）
        logger.warning(
            "process_document 投递失败（文档已上传，可稍后重试）: id=%s err=%s",
            doc_id, exc,
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


# ============================================================
# 4️⃣ 语义检索（Step 4）
# ============================================================


async def search_chunks(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    kb_id: UUID,
    query: str,
    top_k: int = 5,
    min_score: float | None = None,
    document_ids: list[UUID] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """在指定 KB 里做语义检索（pgvector 余弦相似度）。

    流程：校验 KB → query 向量化 → cosine_distance 排序取 Top-K → 组装来源信息。

    Args:
        query: 查询文本
        top_k: 返回前 K 条
        min_score: 可选相似度阈值，只保留 score >= min_score 的
        document_ids: 可选，只检索指定文件的 chunks（按文件选择生成）

    Returns:
        (items, total)；items 是 dict 列表，字段对齐 SearchResultItem。

    Raises:
        KnowledgeError(code="not_found"): KB 不存在/不属于该租户
        KnowledgeError(code="embedding_failed"): 查询向量化失败
    """
    # 1) 校验 KB 存在且属于该租户（复用 get_kb，跨租户直接 404）
    await get_kb(db, tenant_id=tenant_id, kb_id=kb_id)

    # 2) 把 query 向量化
    #    embedding.embed_texts 是同步函数（给 Celery worker 用，内部走 openai 同步客户端）。
    #    在 async 事件循环里直接调会阻塞，所以丢到线程池跑。
    #    延迟 import：避免模块级就加载 openai 客户端。
    from app.services import embedding

    try:
        vectors = await asyncio.to_thread(embedding.embed_texts, [query])
    except embedding.EmbeddingError as exc:
        raise KnowledgeError(
            code="embedding_failed",
            message=f"查询向量化失败: {exc.message}",
        ) from exc
    query_vec = vectors[0]

    # 3) 向量检索：cosine_distance 升序（距离越小越相似），join 文档拿 filename
    #    只检索 READY 文档的 chunk —— PENDING/FAILED 的内容不可信，不参与召回。
    distance = DocumentChunk.embedding.cosine_distance(query_vec)
    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
            DocumentChunk.char_start,
            DocumentChunk.char_end,
            DocumentChunk.content,
            Document.filename,
            distance.label("distance"),
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.tenant_id == tenant_id,
            DocumentChunk.knowledge_base_id == kb_id,
            Document.status == DocumentStatus.READY,
        )
    )

    # 按文件过滤（按文件选择生成：只检索指定文件的 chunks）
    if document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

    stmt = stmt.order_by(distance.asc()).limit(top_k)
    rows = (await db.execute(stmt)).all()

    # 4) 组装结果：score = 1 - cosine_distance（越大越相似），按需用 min_score 过滤
    items: list[dict[str, Any]] = []
    for row in rows:
        score = 1.0 - float(row.distance)
        if min_score is not None and score < min_score:
            continue
        items.append(
            {
                "chunk_id": row.id,
                "document_id": row.document_id,
                "filename": row.filename,
                "chunk_index": row.chunk_index,
                "char_start": row.char_start,
                "char_end": row.char_end,
                "content": row.content,
                "score": score,
            }
        )

    logger.info(
        "search done: kb=%s top_k=%d hits=%d min_score=%s",
        kb_id, top_k, len(items), min_score,
    )
    return items, len(items)
