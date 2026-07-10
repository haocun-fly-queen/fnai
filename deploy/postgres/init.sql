-- pgvector 扩展 + RLS 启用
-- 该脚本在 PostgreSQL 首次启动时执行

-- 启用必要扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";

-- 注意：RLS 的策略在应用代码中通过 Alembic 迁移创建
-- 这里只确保基础能力可用
