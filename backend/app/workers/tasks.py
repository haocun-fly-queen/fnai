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
