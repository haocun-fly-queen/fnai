# ADR 0002: 后端技术栈选型

- **状态：** Accepted
- **日期：** 2026-06-18
- **决策人：** 苏苏、后端主程
- **影响范围：** 后端开发、运维、AI 管线

## 背景与问题

需要选择后端技术栈，约束：
- 团队 3 名后端开发者
- 需要支持异步任务（AI 生成）
- 需要支持多租户隔离
- 需要向量检索（pgvector）
- 4 个月内交付 V1

## 考虑的选项

### 选项 A：FastAPI + SQLAlchemy 2.0 async + PostgreSQL 15 + pgvector + Celery

- 优点：异步原生支持；类型提示完善；Pydantic v2 强类型；pgvector 同库部署减少组件
- 缺点：相比 Django 管理后台需要自己造轮子

### 选项 B：Django + DRF + Celery + 单独向量库（Qdrant / Milvus）

- 优点：自带 admin；ORM 成熟
- 缺点：async 支持弱（4.2 之前）；额外组件增加运维复杂度

### 选项 C：NestJS（Node.js）+ TypeORM + PostgreSQL

- 优点：前后端同语言
- 缺点：Python AI 生态不友好；与 OpenAI SDK 集成有摩擦

## 决策

**采用选项 A：FastAPI + SQLAlchemy 2.0 async + PostgreSQL 15 + pgvector + Celery。**

## 理由

1. **AI 生态匹配**：Python 在 LLM 生态（LangChain、OpenAI SDK、pgvector）有绝对优势
2. **异步原生**：SQLAlchemy 2.0 async + asyncpg 处理高并发 I/O 密集型任务（AI 调用）更高效
3. **类型安全**：Pydantic v2 + mypy 提供编译期错误检查
4. **同库向量**：pgvector 减少一个独立组件，简化部署、事务一致性强
5. **Celery 成熟**：分布式任务队列是 Python 生态的事实标准

## 后果

### 正面

- AI 集成代码简洁（无 Node/Python 桥接）
- 异步性能优势在 AI 调用场景下显著
- 类型系统帮助早期发现错误

### 负面

- 需要自己写一些 Django 自带的功能（管理后台、ORM 迁移）
- SQLAlchemy 2.0 风格学习曲线
- pgvector 单库容量受限（数据量超 1 亿向量需考虑分库）

### 风险与缓解

- **风险：团队 FastAPI 经验不足**
  - **缓解：** 阶段 5-6 集中培训；引入 Senior Developer 指导
- **风险：pgvector 性能**
  - **缓解：** 阶段 9 调优；必要时降级到独立 Qdrant

## 相关资料

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0 迁移指南](https://docs.sqlalchemy.org/en/20/changelog/migration_20.html)
- [pgvector 性能基准](https://github.com/pgvector/pgvector)
