# Backend (FNAI / FastAPI)

## 开发

```bash
# 1. 启数据库
docker compose -f ../infra/docker-compose.yml up -d postgres redis

# 2. 装依赖（用 uv 或 pip）
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# 3. 复制环境变量
cp .env.example .env
# 编辑 .env，填 OPENAI_API_KEY 等

# 4. 跑迁移
alembic upgrade head

# 5. 启动开发服务器
uvicorn app.main:app --reload --port 8000
```

打开 http://localhost:8000/docs 看 OpenAPI 文档。

## 测试

```bash
pytest                    # 跑全部测试
pytest --cov=app          # 带覆盖率
pytest -k test_health     # 跑指定测试
```

## 代码质量

```bash
ruff check .              # lint
ruff format .             # 格式化
mypy app                  # 类型检查
```

## 迁移

```bash
alembic revision --autogenerate -m "add xxx"
alembic upgrade head
alembic downgrade -1
```

## 项目结构

```
app/
├── api/v1/endpoints/    # 路由（按业务领域拆分文件）
├── core/                # 配置、安全、中间件、错误
├── db/                  # session、alembic、base
├── models/              # SQLAlchemy 模型（V1 阶段 2 开始填充）
├── schemas/             # Pydantic schema
├── services/            # 业务逻辑层
└── workers/             # Celery 任务
```

## 命名与规范

- 文件名：`snake_case.py`
- 类名：`PascalCase`
- 路由：所有路由函数使用 `async def`
- 模型：所有查询必须带 `tenant_id` 过滤（多租户）
- 异常：业务异常用 `ApiError`，不直接抛 `HTTPException`
- 日志：用 `from app.core.logging import logger` 记录结构化日志

## 重要提醒

- 任何数据库查询都必须带 `tenant_id` 过滤
- 任何新模型必须配套 Alembic 迁移
- 任何路由必须有对应的测试覆盖
- 敏感配置必须走 `Settings`，不能硬编码
