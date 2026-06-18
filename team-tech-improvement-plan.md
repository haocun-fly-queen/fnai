# FNAI 团队技术能力提升计划

> 适用对象：FNAI / GEO 内容生产平台研发团队（约 7 人）
> 目标：在 8-10 周内建立可落地的代码质量把控体系，并系统提升团队核心技术能力
> 制定者：Senior Developer（高级开发工程师）
> 制定时间：2026-06-18

---

## 一、当前架构快速评估

### 做得好的地方

| 维度 | 评价 |
|------|------|
| 架构选型 | 模块化单体（Modular Monolith）非常契合 7 人团队 + 1000 并发目标，避免了微服务过早拆分 |
| 数据层 | PostgreSQL 15 + pgvector + async SQLAlchemy 2.0 是成熟组合，HNSW 向量索引合理 |
| 异步任务 | Celery 按队列分优先级（high/default/serp/low/agent）是正确思路 |
| 多租户隔离 | 应用层 `tenant_id` 过滤 + PostgreSQL RLS 双重隔离，安全设计到位 |
| AI 管线 | LLM Router、Prompt Engine、A/B 测试、ContentGuard Agent 设计完整 |
| 部署 | Docker Compose 单机方案适合早期，Nginx 配置考虑了静态资源、限流、SSE |

### 主要风险与能力缺口

| 风险 | 说明 | 优先级 |
|------|------|--------|
| 范围过大 | 14 个阶段、33 周、42 张表，V1 极易延期 | P0 |
| 测试策略缺失 | 文档几乎未提及测试，长期质量难保障 | P0 |
| 无 CI/CD | 手工部署、手工迁移，回归成本高 | P0 |
| 前端三套独立应用 | frontend、admin-super、admin-tenant 各自独立，组件/类型/工具重复 | P1 |
| API 契约执行弱 | 文档约定靠人工同步，容易前后端不一致 | P1 |
| AI 效果难以量化 | Prompt A/B 测试、RAG 检索质量、文章评分需要评估框架 | P1 |
| 成本与性能监控 | 未看到明确的 SLO 和成本告警落地细节 | P1 |
| 开发环境不一致 | Windows 开发 + Ubuntu 生产，Docker 是必须但执行细节多 | P2 |

---

## 二、能力提升总体路线

```
第 1-2 周：工程化基础（规范、工具、Git 工作流）
第 3-4 周：质量门禁（代码审查、测试、API 契约）
第 5-6 周：后端深度（FastAPI/SQLAlchemy/异步/Celery）
第 7-8 周：前端深度（React/TypeScript/Tailwind/状态管理）
第 9-10 周：AI 与数据（RAG、Prompt、pgvector、成本监控）
持续：CI/CD、性能优化、监控、技术分享
```

---

## 三、第 1-2 周：工程化基础

### 3.1 统一代码规范

**后端（Python）**
- 使用 `ruff` 替代 flake8 + black + isort（更快、统一）
- 配置 `pyproject.toml`：行宽 100、Python 3.12 target
- 引入 `mypy` 或基于 Pydantic 的严格类型检查
- 强制 `async def` 路由、SQLAlchemy 2.0 模式

**前端（TypeScript）**
- `eslint` + `prettier` + `@typescript-eslint/recommended-type-checked`
- 禁止 `any`，强制组件 props 接口
- Tailwind 类名排序：使用 `prettier-plugin-tailwindcss`

**提交规范**
- 采用 Conventional Commits：`feat:`, `fix:`, `refactor:`, `test:`, `docs:`
- 每个 PR 必须关联 issue / 任务 ID

### 3.2 引入 Pre-commit Hooks

```yaml
# .pre-commit-config.yaml（后端仓库）
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.10.0
    hooks:
      - id: mypy
```

```json
// package.json scripts（前端仓库）
{
  "lint": "eslint . --ext ts,tsx",
  "lint:fix": "eslint . --ext ts,tsx --fix",
  "format": "prettier --write \"src/**/*.{ts,tsx,css,json}\"",
  "type-check": "tsc --noEmit"
}
```

### 3.3 Git 工作流强化

- 主分支保护：`main` 必须通过 PR + CI 才能合并
- 分支命名规范：`feat/xxx`、`fix/xxx`、`refactor/xxx`、`docs/xxx`
- 每个 PR 必须包含：变更说明、测试证据、影响范围、截图（前端）
- 禁止 `git push --force`（已在 CLAUDE.md 中规定，需团队宣誓）

### 3.4 本周验收

- [ ] 所有仓库都有 `pyproject.toml` / `.eslintrc` / `.prettierrc`
- [ ] 所有仓库都有 `.pre-commit-config.yaml` 并成功安装
- [ ] 主分支开启 PR + CI 保护
- [ ] 团队完成一次规范宣讲

---

## 四、第 3-4 周：质量门禁

### 4.1 代码审查机制

**PR 审查 Checklist（必须项）**

```markdown
## 后端审查清单
- [ ] 所有查询都包含 `tenant_id` 过滤
- [ ] 所有路由都是 `async def`
- [ ] 数据库会话使用 `get_db` 依赖注入，正确 commit/rollback
- [ ] 敏感数据（密码、API Key）已加密或哈希
- [ ] 新增/修改的模型有 Alembic 迁移
- [ ] 异常处理有日志，不吞异常
- [ ] 单元测试覆盖新增业务逻辑

## 前端审查清单
- [ ] 无 `any` 类型
- [ ] API 调用使用统一 Axios 实例
- [ ] 表单使用 React Hook Form + Zod
- [ ] 组件拆分合理，无超大文件
- [ ] 错误状态有 UI 反馈
- [ ] 关键交互有测试或截图

## 数据库审查清单
- [ ] 新表包含 `tenant_id`
- [ ] 时间字段使用 `TIMESTAMPTZ`
- [ ] 枚举使用 CHECK 约束
- [ ] 已评估必要索引
- [ ] 软删除使用 `deleted_at`
- [ ] 分区表考虑归档策略
```

**审查轮值**
- 每个 PR 至少需要 1 名审查者
- 每周轮值一名「质量官」负责检查清单执行率

### 4.2 测试策略落地

**后端测试金字塔**

```
        /\
       /  \
      / 集成\      ← 认证、RAG 检索、文章生成流程
     /______\
    /  单元  \    ← service 层、工具函数、Pydantic schema
   /__________\
  /   类型/静态  \  ← mypy、ruff
 /______________\
```

- **单元测试：** `pytest` + `pytest-asyncio` + `factory-boy` / `faker`
- **集成测试：** `TestClient` + 测试数据库（Docker 临时 PostgreSQL）
- **AI 测试：** Prompt 输出固定 seed 测试、RAG 召回率测试

**前端测试**
- `vitest` 单元测试：工具函数、hooks、store
- `@testing-library/react` 组件测试：登录页、表单验证
- `playwright` 关键流程 E2E：注册 → 创建知识库 → 上传文档 → 生成文章

**测试覆盖率门禁**
- 初期目标：后端 service 层 70%+，前端工具/hooks 60%+
- 随着稳定，逐步提升到 80%+

### 4.3 API 契约优先

**OpenAPI 生成与同步**
- 后端用 FastAPI 原生 OpenAPI：`/docs` 和 `/openapi.json`
- 每次后端 PR 合并后，CI 自动生成 OpenAPI JSON 并提交到 `docs/api-contracts/`
- 前端使用 `openapi-typescript` 从 OpenAPI 生成 TypeScript 类型
- 前后端契约变更必须通过 PR 审查

**API 版本策略**
- V1 使用 `/api/v1/` 前缀
- 重大变更升级 `/api/v2/`，避免破坏性修改

### 4.4 本周验收

- [ ] 后端核心模块（auth、article、knowledge）至少 50% 单元测试覆盖
- [ ] 前端登录/注册流程有组件测试
- [ ] API 契约文档从 OpenAPI 自动生成
- [ ] 审查清单执行率 80%+

---

## 五、第 5-6 周：后端核心技术深度

### 5.1 FastAPI 高级模式

**必掌握内容**
- 依赖注入（Dependency Injection）：`get_db`、`get_current_user`、`get_tenant`
- 异常处理：统一 HTTPException + 自定义业务异常
- 中间件：请求日志、租户上下文注入、限流
- 后台任务：`BackgroundTasks` 与 Celery 的选择
- 文件上传：Streaming + 临时文件 + 安全校验

**团队学习目标**
- 每人能独立写出带租户隔离的 CRUD API
- 理解 `async def` 与 `def` 在 FastAPI 中的区别
- 掌握 SQLAlchemy 2.0 async 模式（`select()`、`execute()`、`scalar()`）

### 5.2 SQLAlchemy 2.0 async + 多租户

**关键模式**

```python
# 正确：所有查询带 tenant_id
async def list_articles(db: AsyncSession, tenant_id: UUID):
    result = await db.execute(
        select(Article)
        .where(Article.tenant_id == tenant_id)
        .where(Article.deleted_at.is_(None))
        .order_by(Article.created_at.desc())
    )
    return result.scalars().all()

# 正确：使用 relationship 的 lazy='raise' 防止 N+1
class Article(Base):
    __tablename__ = "article"
    user = relationship("User", lazy="raise")
```

**学习主题**
- 避免 N+1：eager loading（`selectinload`、`joinedload`）
- 事务边界：service 层 vs API 层
- 软删除查询习惯
- Alembic 迁移最佳实践：不要在迁移中放业务逻辑

### 5.3 Celery 任务设计

**关键原则**
- 任务幂等：同一任务重复执行不应产生副作用
- 任务可观测：每个任务写入 `task` 表，进度写入 Redis
- 失败处理：max_retries、指数退避、死信队列
- 长任务拆分：文章生成拆分为 outline → section → seo → quality

**团队训练**
- 模拟 LLM 超时，练习 fallback 和重试
- 实现一个完整的长任务进度推送（SSE + Redis）

### 5.4 本周验收

- [ ] 后端所有模块完成租户隔离审计，无遗漏
- [ ] 单元测试覆盖 service 层主要路径
- [ ] 完成 1 次 Celery 长任务拆分重构
- [ ] 团队内部后端技术分享 1 次

---

## 六、第 7-8 周：前端核心技术深度

### 6.1 React 18 + TypeScript 质量

**关键规范**
- 函数组件 + hooks，避免 class 组件
- 严格模式：`<StrictMode>` 开启
- 状态管理：
  - 服务端状态用 React Query（TanStack Query）
  - 客户端全局状态用 Zustand
  - 避免把所有状态塞进 Zustand
- 性能：
  - 大列表用 `react-window` 或 `tanstack/react-virtual`
  - 避免不必要 re-render：memo、useMemo、useCallback 合理使用

### 6.2 Tailwind + 设计系统

**关键动作**
- 将 `tailwind.config.js` 中的颜色、间距、圆角标准化
- 封装基础组件：`Button`, `Input`, `Card`, `Modal`, `Toast`
- 禁止硬编码颜色值，全部使用 design token
- 主应用用 Tailwind 品牌化风格，管理后台用 Ant Design Pro（已设计，保持）

### 6.3 共享与复用

**问题：** 三个前端项目（frontend、admin-super、admin-tenant）高度重复

**建议方案**
- 提取公共包：`@fnai/shared-ui`（基础组件、hooks、utils）
- 或者至少建立 `packages/shared` monorepo 子目录
- 统一 Axios 实例、错误处理、类型定义
- 如果短期不想引入 monorepo，可用 Git 子模块或 npm workspace 共享

### 6.4 本周验收

- [ ] 前端基础组件库至少覆盖 10 个常用组件
- [ ] 所有 `any` 类型清除或明确豁免
- [ ] 建立前端共享包或至少统一工具目录
- [ ] 完成 1 次前端性能优化分享

---

## 七、第 9-10 周：AI 与数据深度

### 7.1 RAG 质量评估

**关键指标**
- 召回率（Recall）：问题相关 chunk 是否被检索到
- 精确率（Precision）：Top-K 中多少是相关 chunk
- 答案相关性：生成内容是否基于检索内容

**落地方法**
- 建立评估数据集：50-100 个标准 query + 期望引用 chunk
- 定期运行 `rag_eval.py`，对比不同 embedding / top-k / 分块策略
- 记录结果到 `prompt_result` 或专门 eval 表

### 7.2 Prompt Engineering 工程化

**关键原则**
- 提示词模板版本化：存数据库 + Git 双备份
- 变量注入清晰：每个 prompt 有明确的 `variables` schema
- A/B 测试必须定义成功指标：质量评分、用户评分、成本
- 避免过度提示：prompt 越长，成本越高，质量不一定越好

**学习主题**
- Few-shot vs zero-shot 选择
- Chain-of-Thought 在 SEO/GEO 内容生成中的应用
- 输出结构化：强制 JSON 模式 / function calling

### 7.3 LLM 成本与路由

**关键动作**
- 完善 `model_call_log` 分区表清理策略
- 实现成本实时看板：按模型 / 场景 / 租户 / 用户聚合
- 定义每个场景的 SLO：响应时间、成功率、单次成本上限
- 练习 fallback：主模型失败时自动降级到备选模型

### 7.4 pgvector 与性能

**关键调优**
- HNSW 参数：`m` 和 `ef_construction` 根据数据量调整
- 查询时设置 `ef_search`（或 `hnsw.ef_search`）平衡速度与精度
- 定期 `VACUUM ANALYZE` 和索引重建
- 监控向量表大小：kb_chunk 是最大表之一

### 7.5 本周验收

- [ ] 建立 RAG 评估数据集并运行首次评估
- [ ] Prompt 版本管理页面可用（至少后端 API + 简单前端）
- [ ] 成本看板能展示当日/当月模型调用成本
- [ ] 完成 1 次 AI 管线技术分享

---

## 八、持续：CI/CD、监控与性能

### 8.1 CI/CD 流水线

**推荐阶段**

```yaml
# .github/workflows/ci.yml（或 Gitee CI）
name: CI
on: [pull_request]
jobs:
  lint:
    - run: ruff check . / npm run lint
  type-check:
    - run: mypy app / npm run type-check
  test:
    - run: pytest / npm run test
  build:
    - run: docker build .
```

**部署流水线**
- 开发环境：Docker Compose 本地
- 测试环境：每次合并到 `develop` 自动部署
- 生产环境：手动触发 + 蓝绿/滚动发布

### 8.2 监控与告警

**必接指标**
- Sentry：Python 异常、前端错误
- Prometheus + Grafana：CPU、内存、队列深度、API 响应时间
- 业务看板：文章生成成功率、平均生成时间、模型调用成本、WAU/MAU
- 告警通道：钉钉 / 企业微信 / 飞书

### 8.3 性能优化专项

**目标 SLO**
- API p95 响应时间 < 2s（非生成类）
- 文章生成 5000 字 < 30s
- 页面首屏加载 < 1.5s
- 前端动画 60fps

**优化方向**
- 后端：数据库索引、连接池、缓存、异步 IO
- 前端：代码分割、懒加载、图片优化、关键 CSS
- AI：缓存 embedding、提示词压缩、模型降级

---

## 九、团队协作与学习机制

### 9.1 每周技术分享

| 周次 | 主题 | 主讲 |
|------|------|------|
| 1 | 代码规范与 Pre-commit | 后端负责人 |
| 2 | Git 工作流与 PR 审查 | 苏苏 / 总协调 |
| 3 | FastAPI 依赖注入与异步模式 | 后端开发 |
| 4 | SQLAlchemy 2.0 + 多租户 | 数据库负责人 |
| 5 | React Query + Zustand 最佳实践 | 前端开发 |
| 6 | Tailwind 设计系统与组件封装 | 前端开发 |
| 7 | RAG 评估与 Prompt 工程 | AI 工程师 |
| 8 | LLM 成本优化与路由 | AI 工程师 |

### 9.2 架构决策记录（ADR）

- 在 `docs/decisions/` 下记录每个重要技术决策
- 模板：背景、选项、决策、原因、后果、相关人
- 例如：「为什么用模块化单体而非微服务」「为什么用 pgvector 而非单独向量库」

### 9.3 代码审查与导师制

- 苏苏或资深成员作为「质量守门人」每周 review 关键 PR
- 建立「结对编程」机制：后端 + 前端 + AI 跨职能结对
- 每月一次技术回顾：什么做得好、什么需要改进、下月重点

---

## 十、关键交付物清单

| 交付物 | 位置 | 负责 |
|--------|------|------|
| 后端 lint/format 配置 | `backend/pyproject.toml` | 后端 |
| 前端 lint/format 配置 | `.eslintrc`, `.prettierrc`, `tsconfig.json` | 前端 |
| Pre-commit 配置 | `.pre-commit-config.yaml` | 各仓库 |
| CI 工作流 | `.github/workflows/` 或 Gitee CI | DevOps |
| 后端测试基座 | `backend/tests/` + pytest + 测试数据库 | 后端 |
| 前端测试基座 | `frontend/src/__tests__/` + vitest | 前端 |
| API 契约文档 | `docs/api-contracts/*.md` + OpenAPI JSON | 后端 |
| 代码审查 Checklist | `docs/code-review-checklist.md` | 总协调 |
| 架构决策记录 | `docs/decisions/*.md` | 团队 |
| 共享前端包 | `packages/shared-ui/` 或独立仓库 | 前端 |
| RAG 评估集 | `backend/tests/eval/rag_eval.json` | AI |
| 成本监控看板 | 管理后台「模型管理 > 成本分析」页 | 后端 + 前端 |
| 性能监控看板 | Grafana Dashboard | 后端 |

---

## 十一、给苏苏的 3 条 immediate actions

1. **本周内把范围砍一刀**：V1 只保留 P0-P3（基础设施 + 认证 + 知识库 + 文章生成），管理后台、GEO、SERP、计费、流量监控放到 V1.5/V2。42 张表能砍到 20-25 张最好。
2. **立刻建立 CI**：哪怕只是跑 lint + pytest，也比没有强。没有 CI 的代码审查就是形式主义。
3. **指定一名质量官**：让团队每周轮流当一次「质量守门人」，负责检查 PR 是否通过 checklist、测试是否足够、文档是否同步。

---

## 十二、我需要团队提供的信息

为了进一步定制这套方案，请苏苏补充：

1. 团队 7 人里每个人的大致经验和擅长方向（是否有应届生/实习生？）
2. 目前项目实际进度：代码写到哪里了？P0 完成度如何？
3. 团队使用什么代码托管平台？GitHub / Gitee / 其他？
4. 有没有现成的基础设施（服务器、域名、CI 平台）？
5. 你最担心的三个技术风险是什么？

---

*计划制定完成。下一步：苏苏确认方向后，我可以直接帮你们生成第一批配置文件（`.pre-commit-config.yaml`、`pyproject.toml`、CI 工作流、代码审查 checklist 等）。*
