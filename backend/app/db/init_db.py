"""数据库初始化脚本 —— 开发环境用，生产用 alembic。

用途：
    1. 启用 pgvector 扩展
    2. 用 SQLAlchemy Base.metadata.create_all 创建所有表
    3. 验证表是否都建好

⚠️ 跟生产环境 alembic migration 的关系：
    - 开发：改 model → 跑这个脚本 → 表重建（数据会丢！只用于本地）
    - 生产：用 alembic 生成迁移脚本，零停机变更
    - 两者并存没问题：alembic 也是看 Base.metadata 生成差异

为什么不用 alembic？
    - 本项目阶段 1 还没引入 alembic
    - 先用 create_all 跑通业务，等阶段 5（数据/迁移层）再补
    - 真要追：参考 https://alembic.sqlalchemy.org/en/latest/autogenerate.html
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.db.base import Base

# ⚠️ 关键：必须显式 import 所有 model，Base.metadata 才能发现它们
# 这一行是"激活"所有表定义
from app.models import (  # noqa: F401
    Document,
    DocumentChunk,
    Invitation,
    KnowledgeBase,
    Tenant,
    TenantMember,
    User,
)


async def init_database() -> None:
    """建库流程：扩展开启 → 建表 → 验证。"""
    engine = create_async_engine(settings.database_url, echo=False)

    async with engine.begin() as conn:
        # 1️⃣ 启用 pgvector 扩展
        # CREATE EXTENSION IF NOT EXISTS vector;
        # 这一步必须在建表之前，否则 vector(N) 列会报"type vector does not exist"
        print("→ 启用 pgvector 扩展...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        print("  ✓ pgvector 已启用（或已存在）")

        # 2️⃣ 建所有表
        # Base.metadata 会扫所有 import 过的 model，按依赖顺序建表
        print(f"→ 建表（共 {len(Base.metadata.tables)} 张）...")
        await conn.run_sync(Base.metadata.create_all)
        print("  ✓ 表创建完成")

        # 3️⃣ 列出来看效果
        print("→ 当前 DB 里的表：")
        result = await conn.execute(
            text(
                "SELECT tablename FROM pg_tables "
                "WHERE schemaname = 'public' ORDER BY tablename"
            )
        )
        tables = [row[0] for row in result.fetchall()]
        for t in tables:
            marker = "⭐" if t in {"knowledge_bases", "documents", "document_chunks"} else "  "
            print(f"  {marker} {t}")

    await engine.dispose()
    print("\n✅ 数据库初始化完成")


if __name__ == "__main__":
    asyncio.run(init_database())
