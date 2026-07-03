"""文章导出端点（阶段 5）—— Markdown / HTML 导出。

GET /articles/{id}/export?format=markdown
GET /articles/{id}/export?format=html

返回纯文本或完整 HTML 文档（带样式）。
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from markdownify import markdownify as md
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_active_tenant_id, get_db
from app.models.article import Article
from app.schemas.export import ExportFormat

router = APIRouter()


@router.get("/{article_id}/export")
async def export_article(
    article_id: UUID,
    format: ExportFormat = Query(..., description="导出格式：markdown / html"),
    db: AsyncSession = Depends(get_db),
    tenant_id: UUID = Depends(get_active_tenant_id),
) -> Response:
    """导出文章为 Markdown 或 HTML。

    - Markdown: 从 HTML 转换（TipTap 输出是 HTML）
    - HTML: 包装成完整 HTML 文档（带样式、语义化标签）
    """
    # 查询文章（租户隔离）
    stmt = select(Article).where(Article.id == article_id, Article.tenant_id == tenant_id)
    result = await db.execute(stmt)
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="文章不存在")

    if not article.content:
        raise HTTPException(status_code=400, detail="文章内容为空，无法导出")

    # 根据格式返回
    if format == ExportFormat.MARKDOWN:
        # 将 HTML 转为 Markdown
        markdown_content = md(article.content, heading_style="ATX", strip=['script', 'style'])

        # 添加标题
        if article.title:
            markdown_content = f"# {article.title}\n\n{markdown_content}"

        return PlainTextResponse(
            content=markdown_content,
            headers={
                "Content-Disposition": f'attachment; filename="{article.title or "article"}.md"'
            },
        )

    elif format == ExportFormat.HTML:
        # 包装成完整 HTML 文档（带样式）
        html_doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{article.title or "导出文章"}</title>
    <style>
        body {{
            max-width: 800px;
            margin: 40px auto;
            padding: 20px;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            line-height: 1.7;
            color: #334155;
        }}
        h1 {{
            font-size: 2rem;
            font-weight: 700;
            margin-top: 1.5rem;
            margin-bottom: 0.75rem;
            color: #1e293b;
        }}
        h2 {{
            font-size: 1.5rem;
            font-weight: 600;
            margin-top: 1.25rem;
            margin-bottom: 0.625rem;
            color: #334155;
        }}
        h3 {{
            font-size: 1.25rem;
            font-weight: 600;
            margin-top: 1rem;
            margin-bottom: 0.5rem;
            color: #475569;
        }}
        p {{
            margin-top: 0.75rem;
            margin-bottom: 0.75rem;
        }}
        a {{
            color: #3b82f6;
            text-decoration: underline;
        }}
        code {{
            background-color: #f1f5f9;
            color: #e11d48;
            padding: 0.125rem 0.375rem;
            border-radius: 0.25rem;
            font-size: 0.875em;
            font-family: 'Courier New', monospace;
        }}
        pre {{
            background-color: #1e293b;
            color: #e2e8f0;
            padding: 1rem;
            border-radius: 0.5rem;
            overflow-x: auto;
        }}
        pre code {{
            background: none;
            color: inherit;
            padding: 0;
        }}
        blockquote {{
            border-left: 4px solid #cbd5e1;
            padding-left: 1rem;
            margin-left: 0;
            color: #64748b;
            font-style: italic;
        }}
        img {{
            max-width: 100%;
            height: auto;
        }}
    </style>
</head>
<body>
    <h1>{article.title or "未命名文章"}</h1>
    <div class="content">
{article.content}
    </div>
</body>
</html>"""
        return Response(
            content=html_doc,
            media_type="text/html",
            headers={
                "Content-Disposition": f'attachment; filename="{article.title or "article"}.html"'
            },
        )
