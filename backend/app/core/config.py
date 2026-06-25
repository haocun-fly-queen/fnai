"""Application configuration loaded from environment variables.

All env-driven settings live here. Do NOT read os.environ elsewhere.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ----- App -----
    app_name: str = "FNAI Backend"
    app_version: str = "0.1.0"
    environment: Literal["development", "staging", "production", "test"] = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"

    # ----- Server -----
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # ----- Database -----
    database_url: str = "postgresql+asyncpg://fnai:fnai@localhost:5432/fnai_dev"
    database_url_sync: str = "postgresql://fnai:fnai@localhost:5432/fnai_dev"
    db_pool_size: int = 20
    db_max_overflow: int = 10

    # ----- Redis -----
    redis_url: str = "redis://localhost:6379/0"

    # ----- Celery -----
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ----- Auth -----
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # ----- AI -----
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_chat_model: str = "gpt-4o-mini"
    # embedding 向量维度（必须跟模型输出对得上）
    # text-embedding-3-small = 1536
    # text-embedding-3-large = 3072
    # text-embedding-ada-002 = 1536
    embedding_dim: int = 1536

    # ----- Knowledge base / Upload -----
    # 单文件上传上限（字节），默认 200MB
    # 用 200MB 是为了兼顾企业 PDF 白皮书
    max_upload_size_bytes: int = 200 * 1024 * 1024
    # 文本分块配置
    chunk_size: int = 500        # 每段 500 字
    chunk_overlap: int = 50      # 段间重叠 50 字（避免切断语义）
    # 支持的 MIME types
    allowed_mime_types: list[str] = Field(
        default_factory=lambda: [
            "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",  # .docx
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",  # .pptx
            "text/plain",         # .txt
            "text/markdown",      # .md
        ]
    )

    # ----- Storage -----
    s3_endpoint: str = "localhost:9000"
    s3_access_key: str = "fnai"
    s3_secret_key: str = "fnai-secret"
    s3_bucket: str = "fnai-storage"

    # ----- Monitoring -----
    sentry_dsn: str = ""

    # ----- Rate limit -----
    rate_limit_per_minute: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
