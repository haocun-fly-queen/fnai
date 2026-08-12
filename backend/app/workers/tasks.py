# 概念：文档处理异步任务（Celery Task）
#   把"上传后该做的脏活累活"打包成一个后台任务：
#     读文件 → 解析成文本 → 切分 → 算向量 → 写 chunks → 标记 READY。
#   用户上传时 FastAPI 立刻返回（status=PENDING），这个任务在 worker 进程异步跑。
#   Java 对照：≈ 一个 @Async 方法 / MQ 消费者，处理完更新业务状态。
#
# 模块：backend/app/workers/tasks.py。
#   被 celery_app.py 的 include 注册；FastAPI 通过 process_document.delay(doc_id) 投递。
#
# 作用：
#   输入：doc_id（字符串形式的 UUID，Celery 用 json 序列化所以传 str）
#   产出（副作用）：写 document_chunks 表 + 更新 documents.status/chunk_count/error_message
#   不干什么：不返回业务数据给调用方（结果都落 DB，调用方轮询 DB 看状态）。
#
# 怎么写：
#   - 用同步 session（sync_session_scope），不掺 async。
#   - 状态机：先置 PROCESSING；成功置 READY；任何异常置 FAILED + 记 error_message。
#   - 关键设计——状态落库要独立提交：处理失败时，得保证 FAILED 状态能写进去，
#     所以失败分支用"新开一个 session"写状态，避免和出错的 session 搅在一起。
#   - autoretry：embedding 限流等"临时性错误"由 tenacity 在 embedding 层重试；
#     这里对整个任务再加一层 Celery 重试（max_retries=2），兜底网络抖动。
#   - 幂等：重复处理同一个 doc 时先删旧 chunks，避免 chunk_index 唯一约束冲突。

import asyncio
import logging
from uuid import UUID

from celery import shared_task
from sqlalchemy import delete as sa_delete
from sqlalchemy import select

from app.db.session import sync_session_scope
from app.models import Document, DocumentChunk, DocumentStatus
from app.services import chunker, embedding, parser, storage

logger = logging.getLogger(__name__)


@shared_task(
    name="app.workers.tasks.process_document",
    bind=True,
    max_retries=2,
    default_retry_delay=10,
)
def process_document(self, doc_id: str) -> dict:  # noqa: ANN001
    """处理一篇上传的文档（解析→切分→向量化→入库）。

    Args:
        doc_id: 文档 UUID（字符串）

    Returns:
        摘要 dict（写进 Celery result backend，方便调试）：
            {"doc_id": ..., "status": "ready", "chunk_count": N}

    状态机：
        PENDING → PROCESSING → READY
                          ↘ FAILED（解析/向量化失败，记 error_message）
    """
    doc_uuid = UUID(doc_id)
    logger.info("process_document start: doc_id=%s", doc_id)

    try:
        # ---- 1) 取文档 + 置 PROCESSING ----
        with sync_session_scope() as db:
            doc = db.get(Document, doc_uuid)
            if doc is None:
                logger.warning("process_document: doc 不存在 doc_id=%s", doc_id)
                return {"doc_id": doc_id, "status": "not_found"}
            # 已经处理好了就跳过（幂等：防重复投递）
            if doc.status == DocumentStatus.READY:
                logger.info("process_document: 已 READY，跳过 doc_id=%s", doc_id)
                return {"doc_id": doc_id, "status": "ready", "chunk_count": doc.chunk_count}

            doc.status = DocumentStatus.PROCESSING
            doc.error_message = None
            storage_key = doc.storage_key
            content_type = doc.content_type
            tenant_id = doc.tenant_id
            kb_id = doc.knowledge_base_id
        # session 退出时 commit，PROCESSING 状态已落库

        # ---- 2) 读原始文件 ----
        file_path = storage.get_path(storage_key)
        data = file_path.read_bytes()

        # ---- 3) 解析成纯文本 ----
        text = parser.parse(data, content_type)
        if not text.strip():
            raise parser.ParseError(
                "未能从文件中提取到任何文本（可能是扫描件/纯图片，暂不支持 OCR）"
            )

        # ---- 4) 切分 ----
        chunks = chunker.chunk_text(text)
        if not chunks:
            raise parser.ParseError("文本切分后为空")

        # ---- 5) 向量化（批量）----
        vectors = embedding.embed_texts([c.text for c in chunks])

        # ---- 6) 写 chunks + 置 READY（先删旧 chunks 保证幂等）----
        with sync_session_scope() as db:
            db.execute(
                sa_delete(DocumentChunk).where(
                    DocumentChunk.document_id == doc_uuid
                )
            )
            for c, vec in zip(chunks, vectors, strict=True):
                db.add(
                    DocumentChunk(
                        tenant_id=tenant_id,
                        knowledge_base_id=kb_id,
                        document_id=doc_uuid,
                        chunk_index=c.index,
                        content=c.text,
                        content_length=len(c.text),
                        char_start=c.char_start,
                        char_end=c.char_end,
                        embedding=vec,
                    )
                )
            doc = db.get(Document, doc_uuid)
            if doc is not None:
                doc.status = DocumentStatus.READY
                doc.chunk_count = len(chunks)
                doc.error_message = None

        logger.info(
            "process_document done: doc_id=%s chunks=%d", doc_id, len(chunks)
        )
        return {"doc_id": doc_id, "status": "ready", "chunk_count": len(chunks)}

    except (embedding.EmbeddingError,) as exc:
        # embedding 失败可能是临时限流——交给 Celery 再重试一轮
        logger.warning("process_document embedding 失败，准备重试: %s", exc)
        _mark_failed(doc_uuid, f"向量化失败: {exc.message}")
        raise self.retry(exc=exc)

    except Exception as exc:
        # 解析失败等"确定性错误"，不重试，直接标 FAILED
        logger.exception("process_document 失败: doc_id=%s", doc_id)
        msg = getattr(exc, "message", None) or str(exc)
        _mark_failed(doc_uuid, msg)
        return {"doc_id": doc_id, "status": "failed", "error": msg}


def _mark_failed(doc_uuid: UUID, message: str) -> None:
    """把文档标记为 FAILED（独立 session，保证状态一定能落库）。

    截断 error_message 防止超长。
    """
    try:
        with sync_session_scope() as db:
            doc = db.get(Document, doc_uuid)
            if doc is not None:
                doc.status = DocumentStatus.FAILED
                doc.error_message = message[:2000]
    except Exception:
        logger.exception("_mark_failed 写状态也失败了: doc_id=%s", doc_uuid)


# ============================================================
# 文章生成任务（Phase 2 — 批量生成）
# ============================================================


@shared_task(
    name="app.workers.tasks.generate_article_task",
    bind=True,
    max_retries=0,
)
def generate_article_task(self, article_id: str, user_id: str) -> dict:  # noqa: ANN001
    """后台生成一篇文章（四阶段 pipeline）。

    由 batch-generate 端点投递，串行执行（worker prefetch=1）避免千问限流。

    注意：generate_article 是 async 函数且需要 AsyncSession，
    所以整个逻辑都包在 asyncio.run() 里，用 async session_scope()。

    Args:
        article_id: 文章 UUID（字符串）
        user_id: 操作人 UUID（字符串）

    Returns:
        摘要 dict: {"article_id": ..., "status": "completed" / "failed"}
    """
    article_uuid = UUID(article_id)
    logger.info("generate_article_task start: article_id=%s", article_id)

    try:
        result = asyncio.run(_generate_article_async(article_uuid, UUID(user_id)))
        logger.info("generate_article_task done: article_id=%s status=%s", article_id, result.get("status"))
        return result
    except Exception as exc:
        logger.exception("generate_article_task 失败: article_id=%s", article_id)
        msg = getattr(exc, "message", None) or str(exc)
        _mark_generation_failed(article_uuid, msg)
        return {"article_id": article_id, "status": "failed", "error": msg}


async def _generate_article_async(article_uuid: UUID, user_uuid: UUID) -> dict:
    """异步生成文章（在 asyncio.run 里调用）。"""
    from app.db.session import session_scope
    from app.models import Article, ArticleStatus
    from app.services.generation import generate_article

    async with session_scope() as db:
        article = await db.get(Article, article_uuid)
        if article is None:
            logger.warning("_generate_article_async: article 不存在 id=%s", article_uuid)
            return {"article_id": str(article_uuid), "status": "not_found"}

        tenant_id = article.tenant_id

        await generate_article(
            db,
            tenant_id=tenant_id,
            user_id=user_uuid,
            article=article,
        )
        await db.refresh(article)
        status = article.status.value if hasattr(article.status, "value") else str(article.status)

    return {"article_id": str(article_uuid), "status": status}


def _mark_generation_failed(article_uuid: UUID, message: str) -> None:
    """把文章标记为生成 FAILED（独立 session，保证状态落库）。"""
    try:
        with sync_session_scope() as db:
            from app.models import Article, ArticleStatus

            article = db.get(Article, article_uuid)
            if article is not None:
                article.status = ArticleStatus.FAILED
                article.error_message = message[:2000]
    except Exception:
        logger.exception("_mark_generation_failed 也失败了: article_id=%s", article_uuid)


# ============================================================
# 定时发布任务（Phase 2 Step 13）
# ============================================================


@shared_task(
    name="app.workers.tasks.publish_scheduled_articles",
    bind=True,
    max_retries=0,
)
def publish_scheduled_articles(self) -> dict:  # noqa: ANN001
    """Celery Beat 定时任务：发布到期的定时文章。

    查询条件：
        - scheduled_at <= now（已到发布时间）
        - is_published = False（未发布过）
        - status = 'completed'（已生成完成）

    对每篇文章，找到该租户的所有 active 发布目标，逐个发布。
    发布成功后标记 is_published = True。

    Returns:
        {"checked": N, "published": M, "failed": K, "skipped": J}
    """
    logger.info("publish_scheduled_articles: 开始检查定时发布任务")

    try:
        result = asyncio.run(_publish_scheduled_async())
        logger.info("publish_scheduled_articles: 完成 %s", result)
        return result
    except Exception as exc:
        logger.exception("publish_scheduled_articles 失败: %s", exc)
        return {"checked": 0, "published": 0, "failed": 0, "skipped": 0, "error": str(exc)}


async def _publish_scheduled_async() -> dict:
    """异步执行定时发布逻辑。"""
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.db.session import session_scope
    from app.models import Article, ArticleStatus
    from app.models.publish_log import PublishLog, PublishStatus
    from app.models.publish_target import PublishTarget
    from app.services.publishers import get_publisher, PublishResult
    from app.core.config_crypto import decrypt_config

    stats = {"checked": 0, "published": 0, "failed": 0, "skipped": 0}
    now = datetime.now(timezone.utc)

    async with session_scope() as db:
        # 查找到期的定时文章
        stmt = select(Article).where(
            Article.scheduled_at.isnot(None),
            Article.scheduled_at <= now,
            Article.is_published == False,  # noqa: E712
            Article.status == ArticleStatus.COMPLETED,
        )
        result = await db.execute(stmt)
        articles = result.scalars().all()
        stats["checked"] = len(articles)

        for article in articles:
            # 查找该租户的 active 发布目标
            target_stmt = select(PublishTarget).where(
                PublishTarget.tenant_id == article.tenant_id,
                PublishTarget.is_active == True,  # noqa: E712
            )
            target_result = await db.execute(target_stmt)
            targets = target_result.scalars().all()

            if not targets:
                logger.warning(
                    "定时发布: article %s 没有 active 发布目标，跳过",
                    article.id,
                )
                stats["skipped"] += 1
                continue

            any_success = False
            for target in targets:
                try:
                    publisher = get_publisher(target.type)
                    config = decrypt_config(target.type, target.config)

                    # 创建发布日志
                    log = PublishLog(
                        article_id=article.id,
                        target_id=target.id,
                        status=PublishStatus.PENDING,
                    )
                    db.add(log)
                    await db.flush()

                    result: PublishResult = await publisher.publish(
                        article=article,
                        config=config,
                        options={"status": "publish"},
                        db=db,
                        target_id=target.id,
                    )

                    if result.success:
                        log.status = PublishStatus.SUCCESS
                        log.remote_id = result.remote_id
                        any_success = True
                        logger.info(
                            "定时发布成功: article=%s target=%s",
                            article.id, target.name,
                        )
                    else:
                        log.status = PublishStatus.FAILED
                        log.error_message = result.message
                        logger.warning(
                            "定时发布失败: article=%s target=%s err=%s",
                            article.id, target.name, result.message,
                        )
                except Exception as e:
                    logger.exception(
                        "定时发布异常: article=%s target=%s",
                        article.id, target.name,
                    )
                    # 记录失败日志
                    log = PublishLog(
                        article_id=article.id,
                        target_id=target.id,
                        status=PublishStatus.FAILED,
                        error_message=str(e)[:2000],
                    )
                    db.add(log)

            if any_success:
                article.is_published = True
                stats["published"] += 1
            else:
                stats["failed"] += 1

        await db.commit()

    return stats


@shared_task(
    name="app.workers.tasks.batch_publish_task",
    bind=True,
    max_retries=0,
)
def batch_publish_task(
    self,
    article_id: str,
    target_id: str,
    status: str = "draft",
    user_id: str | None = None,
) -> dict:
    """后台把一篇文章发布到一个目标。

    由 batch-publish 端点为每个 (文章, 目标) 组合投递一个任务，
    串行执行（worker prefetch=1）避免平台限流。

    发布结果落 PublishLog，调用方轮询 GET /articles/{id}/publish-logs 查看。

    Args:
        article_id: 文章 UUID（字符串）
        target_id: 发布目标 UUID（字符串）
        status: WordPress status（draft / publish），其他平台忽略
        user_id: 操作人 UUID（字符串），可选

    Returns:
        {"article_id", "target_id", "status": "success"/"failed"/"skipped", ...}
    """
    logger.info(
        "batch_publish_task start: article=%s target=%s", article_id, target_id
    )
    try:
        result = asyncio.run(
            _batch_publish_async(
                UUID(article_id),
                UUID(target_id),
                status,
                UUID(user_id) if user_id else None,
            )
        )
        logger.info(
            "batch_publish_task done: article=%s target=%s status=%s",
            article_id, target_id, result.get("status"),
        )
        return result
    except Exception as exc:
        logger.exception(
            "batch_publish_task 失败: article=%s target=%s", article_id, target_id
        )
        return {
            "article_id": article_id,
            "target_id": target_id,
            "status": "failed",
            "error": str(exc),
        }


async def _batch_publish_async(
    article_uuid: UUID,
    target_uuid: UUID,
    status: str,
    user_uuid: UUID | None,
) -> dict:
    """异步执行单篇单目标发布（在 asyncio.run 里调用）。"""
    from app.core.config_crypto import decrypt_config
    from app.db.session import session_scope
    from app.models import Article
    from app.models.publish_log import PublishLog, PublishStatus
    from app.models.publish_target import PublishTarget
    from app.services.publishers import PublishResult, get_publisher

    async with session_scope() as db:
        article = await db.get(Article, article_uuid)
        if article is None or not article.content:
            logger.warning(
                "_batch_publish_async: 文章不存在或内容为空 id=%s", article_uuid
            )
            return {
                "article_id": str(article_uuid),
                "target_id": str(target_uuid),
                "status": "skipped",
                "reason": "article_missing_or_empty",
            }

        target = await db.get(PublishTarget, target_uuid)
        # 校验目标存在、租户一致、且已启用（跨租户发布是越权，必须拦截）
        if (
            target is None
            or target.tenant_id != article.tenant_id
            or not target.is_active
        ):
            logger.warning(
                "_batch_publish_async: 目标无效/禁用/跨租户 target=%s article=%s",
                target_uuid, article_uuid,
            )
            return {
                "article_id": str(article_uuid),
                "target_id": str(target_uuid),
                "status": "skipped",
                "reason": "target_invalid_or_inactive",
            }

        # 创建发布日志（初始 pending）
        log = PublishLog(
            article_id=article_uuid,
            target_id=target_uuid,
            status=PublishStatus.PENDING,
            created_by=user_uuid,
        )
        db.add(log)
        await db.flush()

        try:
            publisher = get_publisher(target.type)
            config = decrypt_config(target.type, target.config)
            result: PublishResult = await publisher.publish(
                article=article,
                config=config,
                options={"status": status},
                db=db,
                target_id=target.id,
            )

            if result.success:
                log.status = PublishStatus.SUCCESS
                log.remote_id = result.remote_id
                article.is_published = True
                await db.commit()
                return {
                    "article_id": str(article_uuid),
                    "target_id": str(target_uuid),
                    "status": "success",
                    "remote_id": result.remote_id,
                }
            else:
                log.status = PublishStatus.FAILED
                log.error_message = (result.message or "")[:2000]
                await db.commit()
                return {
                    "article_id": str(article_uuid),
                    "target_id": str(target_uuid),
                    "status": "failed",
                    "error": result.message,
                }
        except Exception as e:
            log.status = PublishStatus.FAILED
            log.error_message = str(e)[:2000]
            await db.commit()
            raise
