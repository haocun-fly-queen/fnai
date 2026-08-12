"""Article 业务逻辑（阶段 4 Step 2）。

⚠️ 实现范围：
    - 文章增删改查
    - 版本快照（手工触发）
    - 系统模板列表查询
    - 不含生成 pipeline（那是 Step 3）

风格跟 services/knowledge.py 完全一致：
- 模块级 async 函数
- 业务异常 → ArticleError(code, message) → 端点翻译成 4xx
- 所有查询带 tenant_id 过滤
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models import (
    Article,
    ArticleStatus,
    ArticleVersion,
    PromptTemplate,
)


# ============================================================
# 业务异常
# ============================================================


class ArticleError(Exception):
    """文章业务异常。端点层翻译成 4xx。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# ============================================================
# 工具
# ============================================================


def _count_words(text: str) -> int:
    """简单字数统计：中文按字符算，英文按空格分词加总。

    不追求绝对精确——主要给前端排序用。
    """
    if not text:
        return 0
    # 中文字符 + 英文单词数的近似
    cn = sum(1 for c in text if "一" <= c <= "鿿")
    en_words = len([w for w in text.split() if any(c.isascii() and c.isalpha() for c in w)])
    return cn + en_words


# ============================================================
# 1️⃣ 文章 CRUD
# ============================================================


async def create_article(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    title: str,
    topic: str,
    template_code: str,
    knowledge_base_id: UUID | None,
    content: str,
    source_document_ids: list[UUID] | None = None,
    scheduled_at: datetime | None = None,
) -> Article:
    """创建一篇文章（手工/为生成准备占位）。

    校验：
        - template_code 必须存在于 prompt_templates 表（系统或本租户的）
    """
    # 校验模板存在
    tpl = await _resolve_template(db, tenant_id=tenant_id, code=template_code)
    if tpl is None:
        raise ArticleError(
            code="template_not_found",
            message=f"模板 '{template_code}' 不存在",
        )

    # UUID 转字符串：JSONB 列不能直接存 UUID 对象
    doc_ids_str = (
        [str(uid) for uid in source_document_ids]
        if source_document_ids
        else None
    )

    article = Article(
        tenant_id=tenant_id,
        knowledge_base_id=knowledge_base_id,
        template_code=template_code,
        title=title,
        topic=topic,
        content=content,
        source_document_ids=doc_ids_str,
        scheduled_at=scheduled_at,
        status=ArticleStatus.DRAFT,
        word_count=_count_words(content),
        created_by=user_id,
    )
    db.add(article)
    await db.commit()
    await db.refresh(article)
    logger.info("Article created: id=%s tenant=%s", article.id, tenant_id)
    return article


async def list_articles(
    db: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[list[Article], int]:
    """列出当前租户的所有文章（按创建时间倒序）。"""
    stmt = (
        select(Article)
        .where(Article.tenant_id == tenant_id)
        .order_by(Article.created_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), len(rows)


async def get_article(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    article_id: UUID,
) -> Article:
    """取单篇文章详情（按租户过滤）。"""
    stmt = select(Article).where(
        Article.id == article_id,
        Article.tenant_id == tenant_id,
    )
    article = await db.scalar(stmt)
    if article is None:
        raise ArticleError(code="not_found", message="文章不存在或不属于当前租户")
    return article


async def update_article(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    article_id: UUID,
    title: str | None = None,
    content: str | None = None,
    seo_meta: dict[str, Any] | None = None,
) -> Article:
    """更新文章字段（编辑器保存）。只更新非 None 的字段。"""
    article = await get_article(db, tenant_id=tenant_id, article_id=article_id)
    if title is not None:
        article.title = title
    if content is not None:
        article.content = content
        article.word_count = _count_words(content)
    if seo_meta is not None:
        article.seo_meta = seo_meta
    # 用户编辑过、且当前是 DRAFT，提升到 COMPLETED（有内容了）
    if article.content and article.status == ArticleStatus.DRAFT:
        article.status = ArticleStatus.COMPLETED
    await db.commit()
    await db.refresh(article)
    return article


async def delete_article(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    article_id: UUID,
) -> None:
    """删除文章（CASCADE 删 versions + generation_tasks）。"""
    # 先校验存在
    await get_article(db, tenant_id=tenant_id, article_id=article_id)
    await db.execute(sa_delete(Article).where(Article.id == article_id))
    await db.commit()
    logger.info("Article deleted: id=%s", article_id)


# ============================================================
# 2️⃣ 版本快照
# ============================================================


async def save_version(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    article_id: UUID,
    user_id: UUID,
    note: str | None = None,
) -> ArticleVersion:
    """打一个文章快照（手工触发的"保存版本"）。"""
    article = await get_article(db, tenant_id=tenant_id, article_id=article_id)

    # 计算下一个版本号
    max_no = await db.scalar(
        select(func.coalesce(func.max(ArticleVersion.version_no), 0)).where(
            ArticleVersion.article_id == article_id,
        )
    )
    next_no = int(max_no or 0) + 1

    version = ArticleVersion(
        article_id=article_id,
        tenant_id=tenant_id,
        version_no=next_no,
        title=article.title,
        content=article.content,
        note=note,
        created_by=user_id,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    logger.info("Version saved: article=%s v%d", article_id, next_no)
    return version


async def list_versions(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    article_id: UUID,
) -> tuple[list[ArticleVersion], int]:
    """列出某文章的所有历史版本（按版本号倒序）。"""
    # 顺便校验文章归属
    await get_article(db, tenant_id=tenant_id, article_id=article_id)
    stmt = (
        select(ArticleVersion)
        .where(ArticleVersion.article_id == article_id)
        .order_by(ArticleVersion.version_no.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), len(rows)


# ============================================================
# 3️⃣ 模板查询
# ============================================================


async def list_templates(
    db: AsyncSession,
    *,
    tenant_id: UUID,
) -> tuple[list[PromptTemplate], int]:
    """列出可用模板（系统模板 + 本租户自定义模板）。"""
    stmt = (
        select(PromptTemplate)
        .where(
            # 系统模板（tenant_id IS NULL）或者本租户的自定义模板
            (PromptTemplate.tenant_id.is_(None)) | (PromptTemplate.tenant_id == tenant_id),
            PromptTemplate.is_active.is_(True),
        )
        .order_by(PromptTemplate.tenant_id.is_(None).desc(), PromptTemplate.code.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows), len(rows)


async def _resolve_template(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    code: str,
) -> PromptTemplate | None:
    """按 code 找模板：优先本租户自定义，找不到回退系统模板。

    Step 3 生成 pipeline 也会用这个函数。
    """
    # 优先本租户自定义
    tpl = await db.scalar(
        select(PromptTemplate).where(
            PromptTemplate.tenant_id == tenant_id,
            PromptTemplate.code == code,
            PromptTemplate.is_active.is_(True),
        )
    )
    if tpl is not None:
        return tpl
    # 回退系统模板
    return await db.scalar(
        select(PromptTemplate).where(
            PromptTemplate.tenant_id.is_(None),
            PromptTemplate.code == code,
            PromptTemplate.is_active.is_(True),
        )
    )
