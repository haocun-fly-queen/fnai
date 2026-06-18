# FNAI Monorepo

> FNAI / GEO 内容生产平台 — 单一仓库多应用管理

## 仓库结构

```
fnai-monorepo/
├── backend/                # FastAPI + SQLAlchemy 2.0 async 后端
│   ├── app/
│   │   ├── api/v1/         # 路由（按版本）
│   │   ├── core/           # 配置、安全、中间件
│   │   ├── db/             # session、alembic
│   │   ├── models/         # SQLAlchemy 模型
│   │   ├── schemas/        # Pydantic schema
│   │   ├── services/       # 业务逻辑层
│   │   └── workers/        # Celery 任务
│   └── tests/              # pytest
├── frontend/               # Vite + React 18 + TS + Tailwind 主应用
│   ├── src/
│   │   ├── components/     # 通用组件
│   │   ├── pages/          # 页面
│   │   ├── hooks/          # 自定义 hooks
│   │   ├── lib/            # 工具、Axios 实例
│   │   ├── stores/         # Zustand 状态
│   │   └── types/          # TypeScript 类型
│   └── public/
├── admin/                  # 后台管理（Ant Design Pro），V1 暂不实现
├── packages/shared/        # 前后端共享（类型、错误码、API 契约）
│   └── ts/                 # TypeScript 类型 + 错误码常量
├── infra/                  # 部署与基础设施
│   ├── docker-compose.yml  # 本地开发栈
│   ├── prometheus/         # 监控配置
│   └── grafana/            # 仪表盘
├── docs/                   # 项目文档
│   ├── decisions/          # ADR（架构决策记录）
│   ├── code-review-checklist.md
│   ├── commit-convention.md
│   └── phase-1-runbook.md
├── .github/workflows/      # CI
├── .pre-commit-config.yaml
├── .gitignore
├── .editorconfig
├── README.md
└── CONTRIBUTING.md
```

## 快速开始

```bash
# 1. 克隆
git clone <repo-url> fnai-monorepo && cd fnai-monorepo

# 2. 复制环境变量
cp infra/.env.example infra/.env

# 3. 启动开发栈（PostgreSQL + Redis + MinIO）
docker compose -f infra/docker-compose.yml up -d

# 4. 后端
cd backend
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 5. 前端（新开终端）
cd frontend
npm install
npm run dev
# 打开 http://localhost:5173
```

## 端口约定

| 服务 | 端口 | 备注 |
|------|------|------|
| Backend (FastAPI) | 8000 | API 根路径 |
| Frontend (Vite) | 5173 | 主应用 |
| Admin (Ant Design Pro) | 5174 | 管理后台（V1 占位） |
| PostgreSQL | 5432 | 含 pgvector |
| Redis | 6379 | 缓存 + Celery broker |
| MinIO | 9000 / 9001 | S3 兼容对象存储（文件） |
| Prometheus | 9090 | 监控 |
| Grafana | 3000 | 仪表盘 |

## 技术栈版本

- Python 3.12
- Node 22
- PostgreSQL 15 + pgvector
- Redis 7
- FastAPI 0.115+
- SQLAlchemy 2.0+ (async)
- React 18 + Vite 5
- TypeScript 5.4+
- Tailwind 3.4+

## 文档导航

- [V1 范围砍掉清单](./v1-scope-cut-list.md)
- [V1 开发阶段](./v1-development-phases.md)
- [团队技术能力提升计划](./team-tech-improvement-plan.md)
- [阶段 1 Runbook](./docs/phase-1-runbook.md)
- [代码审查 Checklist](./docs/code-review-checklist.md)
- [提交规范](./docs/commit-convention.md)
- [ADR 索引](./docs/decisions/README.md)
