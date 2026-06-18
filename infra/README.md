# Docker Compose 一键起开发栈

## 启动

```bash
# 启动核心栈（PostgreSQL + Redis + MinIO）
docker compose up -d

# 启动监控栈（Prometheus + Grafana）
docker compose --profile monitoring up -d

# 查看日志
docker compose logs -f postgres
```

## 服务

| 服务 | 端口 | 凭证 |
|------|------|------|
| PostgreSQL | 5432 | fnai / fnai |
| Redis | 6379 | 无 |
| MinIO API | 9000 | fnai / fnai-secret |
| MinIO Console | 9001 | fnai / fnai-secret |
| Prometheus | 9090 | 无（profile: monitoring） |
| Grafana | 3000 | admin / admin（profile: monitoring） |

## 数据持久化

数据通过 named volumes 持久化：
- `postgres-data`
- `redis-data`
- `minio-data`
- `grafana-data`

清理数据：`docker compose down -v`

## 初始化

首次启动 PostgreSQL 会执行 `postgres/init.sql`，启用 uuid-ossp / pgcrypto / pgvector 扩展。
