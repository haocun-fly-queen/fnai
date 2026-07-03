"""文章生成 pipeline（阶段 4 Step 3）—— 四阶段管线。

业务背景：
    用户给一个主题 + 选个模板 + 选个知识库，AI 自动写出一篇完整文章。
    用单次 LLM 调用质量不够，FNAI 采用 4 阶段管线：

        1. OUTLINE  —— 生成大纲（标题 + 若干小节 + 每节要点），JSON 格式
        2. SECTION  —— 按大纲逐节生成正文（每节一次 LLM 调用）
        3. SEO      —— 基于成文生成 SEO 元信息（meta_title / desc / keywords）
        4. QUALITY  —— 整篇润色，修错别字、调语气

    每个阶段都用 prompt_templates 表里对应的 prompt，
    并把 RAG 检索回来的相关 chunks 作为上下文喂给 LLM（除 SEO 阶段外）。

设计要点：
    - 主入口 generate_article 是 async，4 个阶段都 await asyncio.to_thread(llm.chat, ...)
      （chat 是同步函数，不阻塞事件循环）
    - 每次 LLM 调用都自动写一条 ModelCallLog（成本审计）
    - 各阶段进度落到 GenerationTask（current_stage / stage_logs / total_tokens）
    - 任何阶段失败：article.status = FAILED + error_message；task.status = FAILED
    - 成功：article.status = COMPLETED + outline/seo_meta/content 全填好；task.status = SUCCEEDED

不在本模块的事：
    - HTTP 端点（services/article.py 之外的 endpoint 调这里）
    - 流式输出（V1 同步返回，SSE 留给以后）
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Article,
    ArticleStatus,
    GenerationStage,
    GenerationStatus,
    GenerationTask,
    ModelCallLog,
    PromptTemplate,
)
from app.services import embedding, llm
from app.services.article import _resolve_template, _count_words
from app.services.knowledge import search_chunks

logger = logging.getLogger(__name__)


# ============================================================
# 业务异常
# ============================================================


class GenerationError(Exception):
    """生成 pipeline 失败。端点层翻译成 5xx。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# ============================================================
# 主入口
# ============================================================


async def generate_article(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    article: Article,
    target_word_count: int | None = None,
) -> Article:
    """对一篇 Article 跑完整 4 阶段生成 pipeline。

    Args:
        article: 已存在的文章对象（status 通常是 DRAFT）

    Returns:
        更新后的 article（status=COMPLETED / FAILED，content/outline/seo_meta 已填）

    Raises:
        GenerationError: 模板不存在等业务问题（pipeline 内部异常会写状态后吞掉，
                        让调用方拿到带 FAILED 状态的 article 而不是抛）
    """
    # 1) 解析模板
    tpl = await _resolve_template(db, tenant_id=tenant_id, code=article.template_code)
    if tpl is None:
        raise GenerationError(
            code="template_not_found",
            message=f"模板 '{article.template_code}' 不存在",
        )

    word_count = target_word_count or tpl.default_word_count

    # 2) 建 GenerationTask（落库,方便观测和审计）
    task = GenerationTask(
        article_id=article.id,
        tenant_id=tenant_id,
        status=GenerationStatus.RUNNING,
        params={
            "topic": article.topic,
            "template_code": article.template_code,
            "knowledge_base_id": str(article.knowledge_base_id) if article.knowledge_base_id else None,
            "target_word_count": word_count,
        },
        stage_logs=[],
        started_at=datetime.now(tz=timezone.utc),
        created_by=user_id,
    )
    db.add(task)
    # 文章先切回 DRAFT（之前可能是 COMPLETED 重新生成）
    article.status = ArticleStatus.DRAFT
    article.error_message = None
    await db.commit()
    await db.refresh(article)
    await db.refresh(task)

    logger.info("Generation start: article=%s task=%s topic=%r", article.id, task.id, article.topic)

    # 3) 跑四阶段（任何一阶段失败 → 标 FAILED）
    try:
        # ── 阶段 1：OUTLINE ──
        outline = await _stage_outline(
            db, task=task, article=article, tpl=tpl,
            word_count=word_count,
        )
        article.outline = outline
        await db.commit()

        # ── 阶段 2：SECTION（逐节）──
        full_content = await _stage_sections(
            db, task=task, article=article, tpl=tpl, outline=outline,
        )
        # 拼成完整 Markdown（加 # 标题 + ## 小节标题）
        markdown = f"# {outline.get('title', article.title)}\n\n"
        for sec, body in zip(outline.get("sections", []), full_content, strict=False):
            markdown += f"## {sec.get('heading', '')}\n\n{body}\n\n"
        article.title = outline.get("title", article.title)
        article.content = markdown.strip()
        await db.commit()

        # ── 阶段 3：SEO ──
        seo_meta = await _stage_seo(
            db, task=task, article=article, tpl=tpl,
            full_content=article.content,
        )
        article.seo_meta = seo_meta
        await db.commit()

        # ── 阶段 4：QUALITY 润色 ──
        polished = await _stage_quality(
            db, task=task, article=article, tpl=tpl,
            full_content=article.content,
        )
        article.content = polished
        article.word_count = _count_words(polished)
        await db.commit()

        # 4) 全部成功
        article.status = ArticleStatus.COMPLETED
        task.status = GenerationStatus.SUCCEEDED
        task.current_stage = None
        task.finished_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(article)
        logger.info(
            "Generation done: article=%s tokens=%d duration_total≈%s",
            article.id, task.total_tokens,
            (task.finished_at - task.started_at).total_seconds() if task.started_at else "?",
        )
        return article

    except Exception as exc:
        # 任何阶段炸：写 FAILED 状态，不让异常冒到端点
        msg = getattr(exc, "message", None) or str(exc)
        article.status = ArticleStatus.FAILED
        article.error_message = msg[:2000]
        task.status = GenerationStatus.FAILED
        task.error_message = msg[:2000]
        task.finished_at = datetime.now(tz=timezone.utc)
        await db.commit()
        await db.refresh(article)
        logger.exception("Generation failed: article=%s", article.id)
        return article


# ============================================================
# 四个阶段实现
# ============================================================


async def _stage_outline(
    db: AsyncSession,
    *,
    task: GenerationTask,
    article: Article,
    tpl: PromptTemplate,
    word_count: int,
) -> dict[str, Any]:
    """阶段 1：生成大纲。

    渲染 prompt → 调 LLM → 解析 JSON → 落库。
    """
    task.current_stage = GenerationStage.OUTLINE
    await db.commit()

    # 拿 RAG 上下文（基于 topic 检索）
    context = await _retrieve_context(
        db, tenant_id=task.tenant_id,
        kb_id=article.knowledge_base_id,
        query=article.topic,
        top_k=5,
    )

    user_prompt = tpl.outline_prompt.format(
        topic=article.topic,
        target_word_count=word_count,
        context=context or "（无相关知识库参考）",
    )

    result = await _call_llm(
        db, task=task, purpose="outline",
        system_prompt="你是 FNAI 平台的内容生成助手，严格按照用户要求输出。",
        user_prompt=user_prompt,
        temperature=0.6,  # 大纲略保守
    )

    # 解析 JSON（LLM 偶尔会带前后说明文字，做一次容错提取）
    outline = _extract_json(result.content)
    if "sections" not in outline:
        raise GenerationError(
            code="outline_invalid",
            message=f"大纲 JSON 缺少 sections 字段：{result.content[:200]}",
        )
    return outline


async def _stage_sections(
    db: AsyncSession,
    *,
    task: GenerationTask,
    article: Article,
    tpl: PromptTemplate,
    outline: dict[str, Any],
) -> list[str]:
    """阶段 2：按大纲逐节生成正文。

    每个小节单独调一次 LLM，单独检索一次相关上下文。
    """
    task.current_stage = GenerationStage.SECTION
    await db.commit()

    sections = outline.get("sections", [])
    bodies: list[str] = []

    for sec in sections:
        heading = sec.get("heading", "")
        points = sec.get("key_points", [])
        # 上下文：按"主题 + 小节标题"组合检索，更精准
        section_query = f"{article.topic} {heading}"
        context = await _retrieve_context(
            db, tenant_id=task.tenant_id,
            kb_id=article.knowledge_base_id,
            query=section_query,
            top_k=3,
        )

        user_prompt = tpl.section_prompt.format(
            topic=article.topic,
            section_title=heading,
            section_points=" / ".join(points),
            context=context or "（无相关参考资料）",
        )

        result = await _call_llm(
            db, task=task, purpose="section",
            system_prompt="你是 FNAI 平台的内容生成助手。",
            user_prompt=user_prompt,
            temperature=0.7,
        )
        bodies.append(result.content.strip())

    return bodies


async def _stage_seo(
    db: AsyncSession,
    *,
    task: GenerationTask,
    article: Article,
    tpl: PromptTemplate,
    full_content: str,
) -> dict[str, Any]:
    """阶段 3：生成 SEO 元信息。"""
    task.current_stage = GenerationStage.SEO
    await db.commit()

    # SEO 不需要 RAG，只看文章本身
    user_prompt = tpl.seo_prompt.format(
        title=article.title,
        full_content=full_content[:6000],  # 太长会超 token，截一下
    )
    result = await _call_llm(
        db, task=task, purpose="seo",
        system_prompt="你是 SEO 专家，输出严格 JSON。",
        user_prompt=user_prompt,
        temperature=0.3,  # SEO 元信息要稳定
    )

    seo = _extract_json(result.content)
    # 容错：缺字段时给默认
    seo.setdefault("meta_title", article.title[:60])
    seo.setdefault("meta_description", "")
    seo.setdefault("keywords", [])
    return seo


async def _stage_quality(
    db: AsyncSession,
    *,
    task: GenerationTask,
    article: Article,
    tpl: PromptTemplate,
    full_content: str,
) -> str:
    """阶段 4：润色（修错别字 / 调语气 / 不大改）。"""
    task.current_stage = GenerationStage.QUALITY
    await db.commit()

    user_prompt = tpl.quality_prompt.format(full_content=full_content)
    result = await _call_llm(
        db, task=task, purpose="quality",
        system_prompt="你是资深编辑，只做润色不改原意。",
        user_prompt=user_prompt,
        temperature=0.3,
    )
    # 容错：润色失败/返回过短 → 退回原文
    polished = result.content.strip()
    if len(polished) < len(full_content) * 0.5:
        logger.warning("quality 返回过短，退回原文: %d -> %d", len(full_content), len(polished))
        return full_content
    return polished


# ============================================================
# 辅助函数
# ============================================================


async def _call_llm(
    db: AsyncSession,
    *,
    task: GenerationTask,
    purpose: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> llm.LLMResult:
    """调一次 LLM，自动写 ModelCallLog 和更新 task 的累计 token / stage_logs。

    LLM 调用本身是同步的，用 asyncio.to_thread 丢到线程池避免阻塞事件循环。
    """
    try:
        result = await asyncio.to_thread(
            llm.chat,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        ok = True
        err: str | None = None
    except llm.LLMError as exc:
        ok = False
        err = exc.message
        result = None

    # 写 ModelCallLog
    db.add(
        ModelCallLog(
            tenant_id=task.tenant_id,
            generation_task_id=task.id,
            purpose=purpose,
            model=result.model if result else "n/a",
            prompt_preview=(result.prompt_preview if result else user_prompt[:1000]),
            response_preview=(result.content[:1000] if result else ""),
            prompt_tokens=result.prompt_tokens if result else 0,
            completion_tokens=result.completion_tokens if result else 0,
            total_tokens=result.total_tokens if result else 0,
            duration_ms=result.duration_ms if result else 0,
            ok=ok,
            error_message=err,
        )
    )

    # 累计到 task
    if result:
        task.total_tokens += result.total_tokens
        # 追加一条 stage_log
        logs = list(task.stage_logs or [])
        logs.append({
            "stage": purpose,
            "tokens": result.total_tokens,
            "duration_ms": result.duration_ms,
            "ok": True,
        })
        task.stage_logs = logs
    await db.commit()

    if not ok or result is None:
        raise GenerationError(
            code=f"{purpose}_failed",
            message=err or "LLM 调用失败",
        )
    return result


async def _retrieve_context(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    kb_id: UUID | None,
    query: str,
    top_k: int,
) -> str:
    """RAG 检索：从指定 KB 拉 top-k 相关 chunks，拼成上下文文本。

    没绑 KB 时返回空串（生成纯模板内容，不带知识）。
    """
    if kb_id is None:
        return ""
    try:
        items, _ = await search_chunks(
            db,
            tenant_id=tenant_id,
            kb_id=kb_id,
            query=query,
            top_k=top_k,
        )
    except Exception as exc:
        logger.warning("RAG 检索失败（跳过上下文）: %s", exc)
        return ""

    if not items:
        return ""
    # 拼成"[来源: xxx.pdf] 内容片段" 的形式
    parts: list[str] = []
    for item in items:
        parts.append(f"【来源：{item['filename']}】\n{item['content']}")
    return "\n\n---\n\n".join(parts)


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出里提取 JSON。容错处理两种常见情况：
       1. 输出直接是 JSON
       2. 输出含 ```json ... ``` 代码块
       3. 输出前后带说明文字，需要找第一个 { 到最后一个 }
    """
    text = text.strip()

    # 情况 2：```json 代码块
    if "```json" in text:
        start = text.find("```json") + len("```json")
        end = text.find("```", start)
        if end != -1:
            text = text[start:end].strip()
    elif text.startswith("```"):
        # 通用 ```...```
        start = text.find("\n") + 1
        end = text.rfind("```")
        if end > start:
            text = text[start:end].strip()

    # 情况 3：截取第一个 { 到最后一个 }
    if not text.startswith("{"):
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last > first:
            text = text[first:last + 1]

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise GenerationError(
            code="json_parse_failed",
            message=f"LLM 输出不是合法 JSON：{exc}；原文前 200 字：{text[:200]}",
        ) from exc
