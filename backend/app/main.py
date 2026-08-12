"""FNAI Backend - FastAPI application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# import sentry_sdk  # 临时禁用 - 网络问题无法安装
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import models so SQLAlchemy registers them on Base.metadata
from app import models  # noqa: F401
from app.api.v1 import api_router
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import logger, setup_logging
from app.db.base import Base
from app.db.session import engine
from app.services import storage


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown hooks."""
    setup_logging()
    # if settings.sentry_dsn:  # 临时禁用 Sentry
    #     sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)
    logger.info("app.startup", env=settings.environment, version=settings.app_version)

    # 确保本地落盘根目录存在
    storage.ensure_storage_root()

    # Dev convenience: auto-create tables on startup. In production, use Alembic.
    if settings.environment == "development":
        try:
            async with engine.begin() as conn:
                # 先开 pgvector 扩展（如果没开）
                from sqlalchemy import text

                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                await conn.run_sync(Base.metadata.create_all)
            logger.info("db.tables_created")
        except Exception as exc:
            logger.error("db.table_creation_failed", error=str(exc))

    yield
    logger.info("app.shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Errors
    register_exception_handlers(app)

    # Routes
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/", tags=["root"])
    async def root() -> dict[str, str]:
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
        }

    return app


app = create_app()
