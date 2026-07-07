# FNAI / GEO 内容生产平台 — 项目交接文档

> 撰写时间：2026-06-25
> 撰写人：Senior Developer（高级开发工程师）
> 适用对象：**接手的其他 AI Agent / 新加入的研发同事**
> 目标：让任何接手的人**5 分钟看懂全局、1 小时能上手改代码**

---

## 📑 文档导览

1. [项目是什么](#1-项目是什么)
2. [技术栈与架构决策](#2-技术栈与架构决策)
3. [代码仓库结构](#3-代码仓库结构)
4. [本地环境怎么搭](#4-本地环境怎么搭)
5. [已完成的工作（截至 2026-06-25）](#5-已完成的工作截至-2026-06-25)
6. [当前 commit 状态](#6-当前-commit-状态)
7. [正在运行的容器](#7-正在运行的容器)
8. [8 个用户使用流程（已跑通）](#8-8-个用户使用流程已跑通)
9. [团队的 4 段模板写作约定](#9-团队的-4-段模板写作约定)
10. [接下来要做的事（按优先级）](#10-接下来要做的事按优先级)
11. [整体 V1 阶段规划（16 周）](#11-整体-v1-阶段规划16-周)
12. [整体落地的最终方案](#12-整体落地的最终方案)
13. [给接手者的具体建议](#13-给接手者的具体建议)
14. [已知问题与风险](#14-已知问题与风险)

---

## 1. 项目是什么

**FNAI**：基于 AI 的 GEO（Generative Engine Optimization，生成式搜索引擎优化）内容生产平台。

**用户故事**：
1. 企业用户注册 → 创建工作空间（tenant）
2. 上传企业资料（PDF/Word/PPT）到知识库
3. AI 自动解析文档、向量化、入库
4. 用户在平台上"写文章" → AI 从知识库检索 + LLM 生成 → 一篇 2000 字 SEO 文章
5. 一键发布到 WordPress 等外部站点

**差异化**：不是 ChatGPT 套壳，是"基于自己企业资料的 GEO 内容工厂"。

**团队**：7 人 = 3 后端 + 2 前端 + 2 AI/算法
**目标**：4 个月内交付 V1（最小可商业闭环）

---

## 2. 技术栈与架构决策

### 后端（**Python**）
| 选型 | 用途 | 为什么选 |
|---|---|---|
| FastAPI 0.115+ | Web 框架 | 异步原生、Pydantic 强类型、OpenAPI 自动生成 |
| SQLAlchemy 2.0 async | ORM | async 友好、Type hints 强 |
| PostgreSQL 15 + pgvector | 数据库 | 一个 DB 存业务 + 向量 |
| Pydantic v2 | 数据校验 | 性能好、类型系统强 |
| Alembic | 迁移 | 标准工具 |
| Celery + Redis | 异步任务 | 长任务（embedding/生成） |
| JWT (python-jose) | 认证 | 无状态、跨域友好 |
| bcrypt | 密码哈希 | 标准 |
| structlog | 日志 | JSON 结构化 |
| pytest | 测试 | 行业标准 |

### 前端
| 选型 | 用途 |
|---|---|
| React 18 + TypeScript | UI |
| Vite 5 | 构建 |
| Tailwind CSS 3 | 样式 |
| Zustand | 状态管理（轻量） |
| Axios | HTTP |
| react-router-dom 6 | 路由 |
| nginx | 生产部署 |

### 基础设施
- **Docker Desktop + WSL2**（开发）
- **Docker Compose**（单机部署）
- **GitHub**（代码托管 + CI）

### 关键 ADR（架构决策记录）

| ADR | 内容 | 位置 |
|---|---|---|
| 0001 | V1 范围重排：42 表 → 22 表，14 阶段 → 7 阶段 | `docs/decisions/0001-v1-scope.md` |
| 0002 | 后端技术栈选型：Python vs Java 选 Python | `docs/decisions/0002-tech-stack.md` |
| 0003 | Monorepo vs Polyrepo：选 Monorepo | `docs/decisions/0003-monorepo.md` |

> **为什么是 Python 不是 Java**（团队背景是 Java 7 人）：AI 生态（LangChain/LlamaIndex/OpenAI SDK）Python 是绝对主流；FastAPI 性能/类型对 Java 同事友好；放弃 Java 换来 AI 生态完整度。

---

## 3. 代码仓库结构

```
E:\workingbuddy\2026-06-18-10-20-53\
├── fnai-monorepo\                  ← 主仓库（git: github.com/haocun-fly-queen/fnai.git）
│   ├── backend\                    ← FastAPI 后端
│   ├── frontend\                   ← React 前端
│   ├── admin\                      ← 管理后台（V1 暂不实现）
│   ├── packages\shared\            ← 前后端共享类型（暂空）
│   ├── infra\                      ← Docker Compose、监控
│   │   ├── docker-compose.yml      ← 全栈（postgres+redis+minio+prometheus+grafana）
│   │   ├── docker-compose.dev.yml  ← 只跑 backend+frontend（复用外部 postgres+redis）
│   │   └── postgres\prometheus\grafana\
│   ├── docs\                       ← 团队规范
│   │   ├── code-review-checklist.md
│   │   ├── commit-convention.md    ← Conventional Commits
│   │   ├── phase-1-runbook.md
│   │   └── decisions\              ← 3 个 ADR
│   ├── scripts\                    ← 后端 E2E 测试（test_kb_e2e.py）
│   ├── CONTRIBUTING.md
│   ├── README.md
│   ├── team-tech-improvement-plan.md   ← 10 周团队能力提升计划
│   ├── v1-scope-cut-list.md            ← V1 砍范围清单
│   └── v1-development-phases.md        ← 7 阶段 16 周规划
├── team-tech-improvement-plan.md
├── v1-development-phases.md
├── v1-scope-cut-list.md
└── docs\                                ← 项目级（写给接手者的文档在这里）
    └── HANDOFF.md                      ← 本文档
└── .workbuddy\                          ← 工具/记忆目录
    ├── memory\2026-06-18.md            ← 详细开发日志（按时间顺序）
    └── storage\                         ← 上传文件落地点（已挂 E 盘）
```

### 后端目录（`backend/app/`）

```
backend/
├── app/
│   ├── main.py                  ← FastAPI 入口
│   ├── core/                    ← 全局基础设施
│   │   ├── config.py            ← Settings（pydantic-settings）
│   │   ├── security.py          ← JWT encode/decode + bcrypt
│   │   ├── errors.py            ← ApiError + 统一异常处理
│   │   └── logging.py           ← structlog
│   ├── db/                      ← 数据库
│   │   ├── base.py              ← SQLAlchemy DeclarativeBase
│   │   ├── session.py           ← AsyncEngine + AsyncSession
│   │   └── init_db.py           ← 开发用：建表（替代 alembic）
│   ├── models/                  ← ORM 模型
│   │   ├── user.py tenant.py membership.py invitation.py
│   │   ├── knowledge_base.py document.py document_chunk.py
│   │   └── __init__.py
│   ├── schemas/                 ← Pydantic DTO（入参/出参）
│   │   ├── auth.py tenant.py membership.py invitation.py knowledge.py
│   │   └── __init__.py
│   ├── services/                ← 业务逻辑
│   │   ├── auth.py tenant.py invitation.py membership.py
│   │   ├── knowledge.py storage.py
│   │   └── __init__.py
│   ├── api/v1/
│   │   ├── deps.py              ← get_current_user + require_role(Role.X) 工厂
│   │   └── endpoints/
│   │       ├── auth.py tenants.py invitations.py memberships.py
│   │       ├── knowledge.py
│   │       ├── demo.py          ← 4 个测权限的桩端点
│   │       └── health.py
│   └── workers/                 ← Celery 任务（空，Step 3 填）
├── scripts/                     ← E2E 测试
│   └── test_kb_e2e.py
├── requirements.txt             ← 主依赖
├── requirements-dev.txt         ← 开发依赖（CI 用）
├── requirements-py38.txt        ← 旧 Python 兼容
├── pyproject.toml               ← ruff/mypy 配置
├── Dockerfile
└── .dockerignore
```

### 前端目录（`frontend/src/`）

```
frontend/
├── src/
│   ├── main.tsx                 ← React 入口
│   ├── App.tsx                  ← 路由配置
│   ├── index.css                ← Tailwind
│   ├── lib/                     ← API 客户端
│   │   ├── api.ts               ← Axios 实例（401 自动跳登录）
│   │   ├── auth-api.ts tenant-api.ts invitation-api.ts membership-api.ts
│   │   ├── demo-api.ts          ← decodeJwtPayload 工具
│   │   └── utils.ts utils.test.ts
│   ├── stores/auth.ts           ← Zustand store（token + user + memberships）
│   ├── components/ProtectedRoute.tsx
│   ├── pages/
│   │   ├── LoginPage.tsx RegisterPage.tsx
│   │   ├── DashboardPage.tsx   ← 工作台（workspace 切换）
│   │   ├── TeamPage.tsx         ← 团队管理（邀请+成员+改角色+踢人）
│   │   ├── AcceptInvitationPage.tsx
│   │   └── TestPanelPage.tsx   ← 开发用，测 4 个权限端点
│   └── types/api.ts             ← 跟后端 schemas 一一对应
├── nginx.conf
├── package.json tsconfig.json
├── Dockerfile .dockerignore .eslintrc.cjs
```

---

## 4. 本地环境怎么搭

### 一次性配置（5 分钟）

```bash
# 1. 装 Docker Desktop（WSL2 后端），启动后等绿色 "Engine running"
# 2. 装 Node 22+ 和 Python 3.12+（或只用 docker 里的）
# 3. clone 仓库
git clone https://github.com/haocun-fly-queen/fnai.git
cd fnai-monorepo

# 4. 启动开发栈（只起 backend + frontend，复用 fnai-dev 网络里的 postgres/redis）
cd infra
docker compose -f docker-compose.dev.yml up -d --build

# 5. 创建数据库表（开发期，替代 alembic）
docker exec fnai-backend-dev python -m app.db.init_db

# 6. 验证
curl http://localhost:8000/api/v1/health    # → {"status":"ok"}
curl http://localhost:3000/                  # → HTML
```

### 端口分配

| 端口 | 服务 | 访问 |
|---|---|---|
| 3000 | Frontend (nginx) | http://localhost:3000 |
| 8000 | Backend (FastAPI) | http://localhost:8000/docs |
| 5432 | PostgreSQL+pgvector | （外部网络共享） |
| 6379 | Redis | （外部网络共享） |
| 9000 | MinIO（暂未起） | http://localhost:9001（控制台） |

### 重要环境变量（compose 里的）

```yaml
DATABASE_URL: postgresql+asyncpg://fnai:fnai@fnai-postgres:5432/fnai_dev
REDIS_URL: redis://fnai-redis:6379/0
JWT_SECRET: dev-only-not-for-production-please-change-me
CORS_ORIGINS: '["http://localhost:3000"]'
OPENAI_API_KEY: ""  # Step 3 才会用
```

---

## 5. 已完成的工作（截至 2026-06-25）

### ✅ 阶段 1（W1-W2 工程化基础）— 完成

- Monorepo 骨架、3 个 ADR、commit 规范、代码审查 checklist
- Docker Compose 全栈 + 开发版（dev 只跑 backend+frontend）
- 后端 FastAPI 最小可运行
- 前端 Vite+React 最小可运行
- GitHub Actions CI（lint + typecheck + build + test）

### ✅ 阶段 2（W3-W4 认证与多租户）— 完成

- **模型**：User, Tenant, TenantMember (含 Role 枚举：OWNER/ADMIN/MEMBER/VIEWER), Invitation
- **认证**：JWT 双 token（access 15min + refresh 7d）、bcrypt 密码
- **多租户**：`tenant_id` 应用层过滤 + token 携带 `active_tenant_id`
- **RBAC**：`require_role(Role.X)` 工厂函数（16 个权限组合测过）
- **邀请系统**：create/list/accept/revoke + auto_accept on register
- **成员管理**：list/change_role/remove + 5 条业务规则
- **前端 6 页**：Login/Register/Dashboard/Team/AcceptInvitation/TestPanel
- **中文 UI**：所有用户可见文字
- **本地 lint 全绿**：ruff ✅ ESLint ✅ prettier ✅ tsc ✅

### ✅ 阶段 3（W5-W7 知识库与 RAG）— 完成（100%）

- ✅ **Step 1**：DB + 模型（knowledge_bases / documents / document_chunks，含 `vector(1536)` + `ivfflat` 索引）
- ✅ **Step 2**：上传接口 + 本地落盘（`/tmp/fnai-storage/`，已挂载 E 盘避免 C 盘满）
- ✅ **Step 3**：Celery 异步处理（解析 → 分块 → embedding）— **已完成（2026-06-26）**
  - `services/parser.py`（PDF/DOCX/PPTX/MD/TXT）、`services/chunker.py`（500字/段 overlap50）、`services/embedding.py`（千问 text-embedding-v2，tenacity 重试）
  - `workers/celery_app.py` + `workers/tasks.py`（`process_document` 状态机 PENDING→PROCESSING→READY/FAILED）
  - compose 加 `celery-worker` 服务；上传后 `process_document.delay()` 触发
  - E2E 跑通：上传→Celery→READY→chunks 带向量（千问真实 embedding，1536 维对齐）
- ✅ **Step 4**：检索 API（pgvector cosine similarity）— **已完成（2026-06-26）**
  - `POST /api/v1/knowledge/{kb_id}/search`：query 向量化 → cosine_distance Top-K → 带文档来源 + score
  - 支持 `top_k`（1-50）+ 可选 `min_score` 阈值过滤；只检索 READY 文档；权限 VIEWER+
  - `services/knowledge.search_chunks`（async 里用 `asyncio.to_thread` 调同步 embedding）
  - E2E 跑通：检索命中带来源、阈值过滤、空 query 422、不存在 KB 404
- ✅ **Step 5**：前端知识库 UI — **已完成（2026-06-26）**
  - `frontend/src/lib/knowledge-api.ts`（列表/创建/上传/文档列表/检索客户端）
  - `frontend/src/pages/KnowledgePage.tsx`（三栏：KB 列表+新建 / 文档上传+状态 / 语义检索）
  - `App.tsx` 加 `/knowledge` 路由；Dashboard 加"知识库 →"入口
  - tsc 类型检查通过；已重新构建前端镜像部署（nginx 静态托管，非热更新，改前端必须 rebuild）
  - ⚠️ 踩坑记录：rebuild 时拉 `nginx:1.27-alpine` 报 401（公司网络），用本地 daocloud 缓存镜像 `docker tag` 成官方名绕过，未改 Dockerfile

### ✅ 阶段 4（W8-W11 文章生成核心）— 完成（100%）

- ✅ **Step 1**：数据模型（5 张表）— **已完成（2026-06-26）**
  - `articles`（标题/正文/状态/大纲/SEO/字数）、`article_versions`（版本快照）、`generation_tasks`（生成任务状态/各阶段日志/token 用量）、`prompt_templates`（四阶段 prompt 配方）、`model_call_logs`（LLM 调用审计）
  - init_db 建表通过（共 12 张表）
  - 踩坑：`datetime` 注解被 `TYPE_CHECKING` 包了导致 SQLAlchemy 运行时解析失败，改成顶层 import 解决
- ✅ **Step 2**：Prompt 模板 + 文章 CRUD — **已完成（2026-06-26）**
  - `db/seed_prompts.py`：5 个系统模板灌库（blog/product/news/seo/social，每个含 outline/section/seo/quality 四阶段 prompt，全部中文）
  - `schemas/article.py`：Create/Update/Read/Summary/Version/Template/GenerationRequest
  - `services/article.py`：CRUD + 版本快照 + 模板查询 + `_resolve_template`（给 Step 3 复用）
  - `api/v1/endpoints/article.py`：7 个 CRUD 端点 + 1 个模板列表（已注册路由）
  - Smoke test 7/7 通过（登录→列模板→创建→编辑→自动 draft→completed→版本快照→删除）
- ✅ **Step 3**：生成 pipeline（四阶段）— **已完成（2026-06-26）**
  - `services/llm.py`：通用 chat completion 客户端（同步函数 + tenacity 重试 429/超时 + LLMResult 含 content/tokens/duration/prompt_preview）
  - `services/generation.py`：四阶段管线 `generate_article`
    - 阶段 1 **OUTLINE**：生成大纲 JSON（标题 + 若干小节 + 每节要点）
    - 阶段 2 **SECTION**：按大纲逐节生成正文（每节单独调 LLM + 单独 RAG 检索 top-3 chunks）
    - 阶段 3 **SEO**：生成 SEO 元信息（meta_title ≤60 / meta_description ≤155 / keywords）
    - 阶段 4 **QUALITY**：整篇润色（修错别字/调语气、不大改）
  - 每阶段自动写 `ModelCallLog`（成本审计）+ 累计更新 `GenerationTask.total_tokens` 和 `stage_logs`
  - RAG 集成：`_retrieve_context` 基于"topic + 小节标题"组合检索，无 KB 时返回空串（纯模板生成）
  - 容错：`_extract_json` 兼容 ```json 代码块/前后说明文字；任何阶段失败 → article.status=FAILED + error_message + task.status=FAILED（异常不冒到端点，让调用方拿到 FAILED 文章而不是 500）
  - 异步桥接：pipeline 是 async，`asyncio.to_thread` 调用同步的 llm.chat 不阻塞事件循环
- ✅ **Step 4**：生成端点（同步返回）— **已完成（2026-06-26）**
  - `POST /api/v1/articles/{id}/generate`：同步触发四阶段，30-90 秒返回完整文章
  - 权限：MEMBER+；请求体可选 `target_word_count`（200-10000，不传用模板默认）
  - 端到端真实验证通过：**67.3 秒生成 1920 字博客文章**（4 小节 + SEO 5 关键词 + 润色），RAG 生效（基于已上传的"E 盘测试"KB 内容），质量自然流畅、有钩子和案例
- ✅ **Step 5**：前端 UI（富文本编辑器）— **已完成（2026-06-29）**
  - `frontend/src/lib/article-api.ts`：文章 API 客户端（CRUD + 生成 + 版本 + 模板）
  - `frontend/src/pages/ArticlesPage.tsx`：文章列表页（创建：选模板/KB/主题 + 状态筛选）
  - `frontend/src/pages/ArticleEditorPage.tsx`：TipTap 富文本编辑器
    - StarterKit + Placeholder 扩展（# 标题 / **加粗` / - 列表 / *斜体*）
    - 生成按钮（触发四阶段管线，loading 提示，完成后自动刷新编辑器）
    - 手动保存 + 版本快照 + 回退历史版本
    - SEO 预览卡片（meta_title / meta_description / keywords）
    - 简易 Markdown ↔ HTML 双向转换（V1 方案，V1.5 可换 tiptap-markdown）
  - `App.tsx` 加 `/articles` 和 `/articles/:id` 路由
  - Dashboard 加"文章管理 →"入口
  - tsc 类型检查通过；已 rebuild 前端镜像部署
  - ⚠️ 踩坑：磁盘满（C 盘 92%），清理 docker 镜像回收 2.4GB 后构建成功

---

## 5.B 阶段 4 已上线的 API 端点（共 8 个）

```
GET    /api/v1/templates                        列可用模板（5 个系统模板）
GET    /api/v1/articles                         列文章
POST   /api/v1/articles                         创建文章（手工/为生成准备）
GET    /api/v1/articles/{id}                    文章详情
PATCH  /api/v1/articles/{id}                    编辑保存
DELETE /api/v1/articles/{id}                    删除
POST   /api/v1/articles/{id}/versions           打版本快照
GET    /api/v1/articles/{id}/versions           列版本历史
POST   /api/v1/articles/{id}/generate           ★ 触发四阶段生成（同步，30-90s）
```

---

## 6. 当前 commit 状态

```
f095270 chore(infra): docker-compose dev setup + backend lint config
871d556 feat(frontend): phase 2+3 - dashboard/team/test-panel pages + Chinese UI
752b4c4 feat(backend): phase 3 step 1+2 - knowledge base models + file upload
e666be3 feat(backend): phase 2 - invitation + membership system
ae0617a feat(backend): phase 2 - auth + multi-tenant
6f5effd Fix/ci final (#4)        ← 团队之前的 commit
2c29a6a chore(ci): bootstrap monorepo with phase 1 scaffolding
```

**当前 `main` 未 commit 的新文件/改动（阶段 3+4 工作区，未 push）**：
- `backend/app/services/`（parser / chunker / embedding / knowledge.search_chunks / llm / generation）
- `backend/app/workers/`（celery_app / tasks）
- `backend/app/models/`（article / article_version / generation_task / prompt_template / model_call_log）
- `backend/app/schemas/article.py`、`backend/app/services/article.py`
- `backend/app/api/v1/endpoints/article.py`、`backend/app/api/v1/__init__.py`
- `frontend/src/lib/knowledge-api.ts`、`frontend/src/pages/KnowledgePage.tsx`
- `infra/docker-compose.dev.yml`（加 celery-worker、补 CELERY_*、加 scripts 挂载）
- `backend/requirements.txt`（加 python-pptx）
- `backend/scripts/test_kb_e2e.py`（Step 3+4 E2E 扩展）
- `docs/ARCHITECTURE-DEEP-DIVE.md`（底层架构学习文档）

**注意**：以上改动**未 commit 也未 push**。接手者第一件事应 `git add . && git commit` 把阶段 3+4 的工作固化。

---

## 7. 正在运行的容器

```bash
docker ps
# 期望看到 5 个：
#   fnai-frontend-dev   (3000 → 80)
#   fnai-backend-dev    (8000 → 8000)
#   fnai-celery-dev     (Celery worker，无端口暴露，消费 Redis 队列)
#   fnai-redis          (6379 → 6379)
#   fnai-postgres       (5432 → 5432, pgvector)
```

> 注意：postgres 和 redis 是**外部容器**（名为 `fnai-postgres` / `fnai-redis`），属于另一个 `fnai-dev_default` Docker 网络。dev compose 文件里通过 `external: true` 复用。

---

## 8. 用户使用流程（已跑通）

| # | 流程 | 路径 | 状态 |
|---|---|---|---|
| 1 | 注册账号（同时建工作空间） | `POST /api/v1/auth/register` | ✅ |
| 2 | 登录拿 token | `POST /api/v1/auth/login` | ✅ |
| 3 | 看自己信息 | `GET /api/v1/auth/me` | ✅ |
| 4 | 列我的工作空间 | `GET /api/v1/tenants/mine` | ✅ |
| 5 | 切换工作空间（换 token） | `POST /api/v1/tenants/switch` | ✅ |
| 6 | 邀请成员（生成 token+链接） | `POST /api/v1/invitations` | ✅ |
| 7 | 接受邀请 | `POST /api/v1/invitations/accept` | ✅ |
| 8 | 列/改/踢成员 | `/api/v1/tenants/{id}/members` | ✅ |
| 9 | 知识库 CRUD | `/api/v1/knowledge` | ✅ |
| 10 | 上传文档 | `POST /api/v1/knowledge/{id}/documents` | ✅ |
| 11 | 列/看/删文档 | `/api/v1/knowledge/{id}/documents` | ✅ |
| 12 | 文档处理（解析+embedding） | Celery 异步 | ✅（Step 3） |
| 13 | 语义检索 | `POST /api/v1/knowledge/{id}/search` | ✅（Step 4） |
| 14 | 列可用模板 | `GET /api/v1/templates` | ✅（阶段 4） |
| 15 | 文章 CRUD | `/api/v1/articles` | ✅（阶段 4） |
| 16 | AI 生成文章（四阶段管线） | `POST /api/v1/articles/{id}/generate` | ✅（阶段 4） |
| 17 | 版本快照 | `/api/v1/articles/{id}/versions` | ✅（阶段 4） |

### E2E 测试脚本

文件：`backend/scripts/test_kb_e2e.py`

```bash
cd /e/workingbuddy/2026-06-18-10-20-53/fnai-monorepo/backend
python -m scripts.test_kb_e2e
```

---

## 9. 团队的 4 段模板写作约定

> 这是苏苏在 2026-06-18 立的规矩，所有新代码模块都要按这个格式讲解。

每个新模块/新函数，**写代码 + 解释时**都要带 4 段：

```python
# 概念：是什么（业务背景、Java 对照）
# 模块：在哪（文件路径、属于哪层）
# 作用：干什么（输入/输出/不干什么）
# 怎么写：实现思路（关键决策、陷阱）
```

详细中文注释写进代码 + 4 段文字说明在对话里输出。

**这是从这天起所有新写的代码都遵守的硬规矩**，接手后不要改这个约定。

---

## 10. 接下来要做的事（按优先级）

### 🔴 P0 — 必须马上做（阻塞 V1）

#### ~~① 阶段 3 Step 3：Celery 异步处理~~ ✅ 已完成（2026-06-26）

#### ~~② 阶段 3 Step 4：检索 API~~ ✅ 已完成（2026-06-26）

#### ~~③ 阶段 3 Step 5：前端知识库 UI~~ ✅ 已完成（2026-06-26）

#### ~~④ 阶段 4 文章生成核心（后端）~~ ✅ 已完成（2026-06-26）
5 张表 + 5 个预置模板 + CRUD + 四阶段生成 pipeline（outline→section→seo→quality）+ 生成端点

#### ~~⑤ 阶段 4 Step 5：前端富文本编辑器~~ ✅ 已完成（2026-06-29）
- TipTap 富文本编辑器（StarterKit + Placeholder）
- 文章列表页 + 创建（选模板/KB/主题）+ 触发生成 + 版本快照 + SEO 预览

#### ⑥ 阶段 5：发布与导出（2 周）
- 2 张表：publish_target / publish_log
- 一键导出 Markdown/HTML
- WordPress REST API 集成
- 简单发布配置页

### 🟢 P2 — V1.5/V2 做

#### ⑦ 阶段 6：联调/压测/安全审计（2 周）
- 100/500/1000 并发压测
- 安全审计（SQL 注入、越权、敏感数据、XSS）
- 故障演练
- 备份恢复演练
- Runbook

#### ⑧ 阶段 7：灰度发布（1 周）
- 5-10 种子客户
- 监控看板
- 收集反馈
- V1.5 范围重排

### ⚪ 基础设施债

- **写正式 pytest 测试**（目前只有手写 E2E 脚本）
- **alembic 迁移**（目前用 `init_db.py` 凑合，阶段 5 前要补）
- **MinIO 切换**（现在用本地落盘，生产必须切对象存储）
- **PostgreSQL RLS**（行级安全策略，目前只应用层过滤）
- **embedding 缓存**（同一文本不重复算）
- **CI 跑通**（目前 CI 配好了但从没成功跑过端到端）

---

## 11. 整体 V1 阶段规划（16 周）

```
W1-W2   ┃ 阶段 1：工程化基础 ✅ 完成
W3-W4   ┃ 阶段 2：认证与多租户 ✅ 完成
W5-W7   ┃ 阶段 3：知识库与 RAG 🔵 30% (Step 1+2 完成)
W8-W11  ┃ 阶段 4：文章生成核心 ✅ 完成
W12-W13 ┃ 阶段 5：发布与导出 ⏳
W14-W15 ┃ 阶段 6：联调/压测/安全审计 ⏳
W16     ┃ 阶段 7：灰度发布与内测 ⏳
```

### V1 范围砍掉的（推迟到 V1.5 / V2）

- 实名认证、SSO、OAuth
- 细粒度权限
- 审计日志
- 网页抓取（Firecrawl）
- Notion/Confluence/飞书集成
- 多模态（图/表）
- 知识图谱
- GEO 优化（地理位置感知）
- A/B 测试
- 智能配图
- 多语言
- 个性化风格学习
- Shopify/Wix/微信公众号集成
- 自动定时发布

详见 `v1-scope-cut-list.md`。

---

## 12. 整体落地的最终方案

> **这一节是写给接手者的"实施路线图"** — 上面第 11 节是"规划蓝图"，这一节是"按什么顺序、用什么方法、怎么验证"。

### 12.1 三步走总策略

我们采用**"地基 → 积木 → 业务"**三阶段交付，每步交付都能让产品跑得起来：

| 步骤 | 主题 | 交付物 | 周期 | 累计 |
|---|---|---|---|---|
| **Step 1** | 团队工程化基础 | 仓库 + Docker + CI + 规范 | W1-W3 | 3 周 |
| **Step 2** | 账号 / 团队 / 协作 | 认证 + 多租户 + 邀请 + RBAC | W4-W8 | 8 周 |
| **Step 3** | 内容生产能力 | 知识库 + 检索 + 文章生成 | W9-W14 | 14 周 |
| **Step 4** | 验收 + 灰度 | 内部测试 + 公测 | W15-W16 | 16 周 |

> **不要跳过 Step 1 去做业务**。我们 1 月份曾经直接撸业务代码，结果 3 周后改一个字段名要全栈搜 20 处。

### 12.2 每个 Step 的具体落地

#### **Step 1：团队工程化基础（W1-W3）**

**目标**：让 7 个 Java 背景的同事**能跑、能改、能测**这个 Python 项目。

| 周 | 任务 | 验收标准 |
|---|---|---|
| W1 | 仓库脚手架（monorepo + Docker Compose） | 一条命令 `make dev` 起 4 个容器 |
| W2 | CI（GitHub Actions）+ 本地 lint 闭环 | PR 自动跑测试 + 阻止不合规代码合并 |
| W3 | 规范文档（commit / code review / 4 段模板） | 团队 review 通过率 > 80% |

**当前状态**：✅ **已完成**。

**关键文件**：
- `infra/docker-compose.dev.yml`、`backend/Dockerfile`、`frontend/Dockerfile`
- `.github/workflows/ci.yml`
- `pyproject.toml`（ruff + mypy 配置）
- `frontend/.eslintrc.cjs`
- `docs/commit-convention.md`、`docs/code-review-checklist.md`

---

#### **Step 2：账号 / 团队 / 协作（W4-W8）**

**目标**：把"账号 + 工作空间 + 团队成员 + 权限"这条主链打通。

| 周 | 任务 | 验收标准 |
|---|---|---|
| W4 | DB schema 设计（3 张表）+ Alembic | 能在 pgAdmin 看到完整 ER 图 |
| W5 | 注册 / 登录 / JWT | curl 测试 6 个场景全过 |
| W6 | 多租户切换 + RBAC 装饰器 | 4 角色 × 4 端点 = 16 组合行为正确 |
| W7 | 邀请 token 体系 | 9 个场景全过（含重放保护、邮箱校验） |
| W8 | 踢人 + 改角色（5 条业务规则） | 13 个场景全过（含"不能踢最后一个 OWNER"） |

**当前状态**：✅ **已完成**（W4-W8 全过）。

**关键文件**：
- `backend/app/models/{user,tenant,membership,invitation}.py`
- `backend/app/api/v1/deps.py`（`require_role(Role.X)` 工厂）
- `backend/app/services/{auth,tenant,invitation,membership}.py`
- `backend/app/api/v1/endpoints/{auth,tenants,invitations,memberships,demo}.py`
- `frontend/src/pages/{LoginPage,RegisterPage,DashboardPage,TeamPage,AcceptInvitationPage,TestPanelPage}.tsx`

---

#### **Step 3：内容生产能力（W9-W14）**

**目标**：用户能把 PDF / Word / 网页喂给平台，平台能基于这些材料**生成 SEO 友好的文章**。

| 周 | 子任务 | 状态 | 交付物 |
|---|---|---|---|
| W9.1 | 知识库 / 文档 / Chunk 三张表 | ✅ | `models/knowledge_base.py`、`document.py`、`document_chunk.py` |
| W9.2 | 文件上传接口 + 落盘 | ✅ | `services/storage.py`、`services/knowledge.py`、8 个端点 |
| W10 | Celery 异步处理（解析 → 切分 → embedding） | ⏳ **下一步** | 4 个 worker 任务 + Celery 服务 |
| W11 | 检索 API（pgvector 相似度搜索） | 📋 | `/knowledge/{id}/search` + Top-K + 引用追溯 |
| W12 | 文章生成 pipeline（RAG + LLM） | 📋 | `/articles/generate` 流式响应 |
| W13 | 前端：知识库管理 + 文章编辑器 | 📋 | `KnowledgePage`、`ArticleEditorPage` |
| W14 | 前端：文章列表 + 详情 + SEO 预览 | 📋 | `ArticlesPage`、`ArticleDetailPage` |

**当前状态**：W9.1 + W9.2 完成（约 30%），W10 是 **P0 第一优先**。

**关键设计**（提前说清楚，W10 接手者直接照做）：

1. **异步处理链路**：
   ```
   用户上传 PDF
     ↓ FastAPI 立即返回 201 + status=pending
     ↓ Celery worker 异步
       ① pypdf / python-docx 解析 → 纯文本
       ② RecursiveCharacterTextSplitter 切分（chunk=500, overlap=50）
       ③ OpenAI text-embedding-3-small 算 embedding（每段 1 次 API 调用）
       ④ 写 document_chunks 表（status 改 ready）
   ```

2. **错误处理**：
   - PDF 解析失败 → `documents.status = failed` + `error_message` 字段记录原因
   - Embedding API 限流（429）→ 指数退避重试 3 次
   - Worker 崩溃 → 30 分钟后 supervisor 自动重启

3. **成本控制**：
   - 单文件超过 50 页 → 提示用户分批上传
   - Chunk 数量超过 500 → 只保留前 500（其余给提示）

---

#### **Step 4：验收 + 灰度（W15-W16）**

| 周 | 任务 |
|---|---|
| W15 | 内部 7 人 + 10 个种子用户实测，bug 修复 |
| W16 | 性能压测（100 并发）+ 灰度发布（先 50% 用户）+ 24h 监控 |

### 12.3 团队分工（7 人怎么干）

> 这是**建议分工**，实际按你团队强项调整。

| 角色 | 人数 | 负责模块 | 技能要求 |
|---|---|---|---|
| **后端核心** | 2 人 | 模型设计 + 业务 service + 端点 | Python 强、SQL 熟、AI 概念懂 |
| **后端 AI** | 1 人 | Celery + Embedding + LLM 调用 | Python + 异步任务 + OpenAI API |
| **前端** | 2 人 | 页面 + 状态管理 + API 集成 | React + TypeScript + Tailwind |
| **DevOps** | 1 人 | Docker + CI + 监控 + 备份 | Docker + K8s + GitHub Actions |
| **测试 / PM** | 1 人 | 测试用例 + 用户验收 + 文档 | 业务理解 + 自动化测试 |

**协作约定**：
- 每个模块 PR 必须有 1 个 reviewer（不能自己合）
- 每天 15 分钟站会（同步阻塞点）
- 每周五 demo（哪怕只完成了 10%，也展示出来）

### 12.4 技术债 vs 业务债

我们**有意识地**积累了一部分技术债，因为业务必须先跑起来：

| 类别 | 项 | 何时还 |
|---|---|---|
| **技术债（必须还）** | 没接 Alembic（用 init_db 凑合） | V1 上线前一周 |
| **技术债（必须还）** | 单点 JWT secret（写 config） | V1 上线前一周（用 KMS） |
| **技术债（必须还）** | 没限流（无 SlowAPI） | W14 收尾 |
| **技术债（应该还）** | 测试覆盖率 < 60% | W15 验收前 |
| **业务债（先欠着）** | 没接 OpenAI（只调 embedding） | W12 直接接 |
| **业务债（先欠着）** | 没用 MinIO（本地落盘） | W11 切 |

> **规则**：标"必须还"的不还不能上线；标"应该还"的尽量还；标"先欠着"的看进度。

### 12.5 验证 / 验收清单

每个 Step 完工必须跑过这套清单：

| 维度 | 检查项 | 通过条件 |
|---|---|---|
| **功能** | E2E 场景数 | 标的所有场景 100% 过 |
| **质量** | ruff / eslint / tsc / mypy | 0 错误 0 警告 |
| **质量** | 测试覆盖率 | 后端 ≥ 60%，前端 ≥ 50% |
| **性能** | 列表页加载 | < 500ms |
| **性能** | 上传 PDF 50MB | < 3s 落盘（不含解析） |
| **安全** | tenant 隔离 | 跨租户访问 100% 拒绝 |
| **安全** | JWT 过期 | 7 天后自动 401 |
| **可观测** | 日志 / 错误 | 关键操作有结构化日志 |
| **可观测** | 健康检查 | `/api/v1/health` 返回 200 |

### 12.6 接手者怎么用这一节

1. **刚接手时**：先看 12.1 总策略 → 再看 12.2 找到你负责的 Step → 看"当前状态"列
2. **要做新任务时**：看 12.2 里你 Step 的"关键设计" → 看 12.3 确认你找谁 review
3. **完工时**：跑 12.5 验证清单 → 不通过不能提 PR
4. **踩坑时**：回 12.4 看是不是"技术债（必须还）"清单里漏的

---

## 13. 给接手者的具体建议

### 接手第一周做什么

1. **读完 5 个核心文档**（按顺序）：
   - `team-tech-improvement-plan.md`（团队目标）
   - `v1-scope-cut-list.md`（V1 范围）
   - `v1-development-phases.md`（7 阶段规划）
   - `docs/HANDOFF.md`（本文件）
   - `.workbuddy/memory/2026-06-18.md`（详细开发日志）

2. **本地环境跑通**（5 分钟）：
   ```bash
   cd fnai-monorepo/infra
   docker compose -f docker-compose.dev.yml up -d --build
   docker exec fnai-backend-dev python -m app.db.init_db
   curl http://localhost:8000/api/v1/health
   ```

3. **跑一次 E2E**（10 秒）：
   ```bash
   cd ../backend
   python -m scripts.test_kb_e2e
   ```

4. **读 3 个关键文件**（理解代码风格）：
   - `backend/app/api/v1/deps.py`（require_role 工厂模式，**全代码最精华**）
   - `backend/app/services/invitation.py`（业务逻辑分层范本）
   - `backend/app/models/document_chunk.py`（pgvector 用法范本）

### 写新功能时的约定

1. **永远 4 段模板**（参见第 9 节）
2. **永远写 E2E 测试**（哪怕先写 happy path）
3. **永远用业务异常**（不要直接 raise HTTPException）
4. **永远加 tenant_id 过滤**（multi-tenant 核心安全线）
5. **永远不写明文密钥**（用环境变量）

### 代码风格要点

- **每写一个业务异常类**，错误码 → HTTP 状态码映射放在 endpoint 文件
- **service 层只接 db/user/参数**，不知道 HTTP
- **endpoint 层只翻译异常 + 检查权限**，不写业务
- **schema 层用 Pydantic v2**，field_validator 替代老 v1 的 validator
- **所有 SQL 走 ORM**，禁止字符串拼接

### 调试技巧

```bash
# 看后端实时日志
docker logs -f fnai-backend-dev

# 进容器里手动跑 Python
docker exec -it fnai-backend-dev python
>>> from app.services import invitation
>>> from app.db.session import AsyncSessionLocal

# 查数据库
docker exec fnai-postgres psql -U fnai -d fnai_dev
>>> \dt                                  # 列出表
>>> SELECT * FROM users LIMIT 5;        # 查数据

# 重启后端（改代码不用重启，--reload 已经开了）
docker restart fnai-backend-dev
```

---

## 14. 已知问题与风险

### 🐛 当前已知

1. **公司网络连不上 GitHub**（push 失败、npm 502 同样原因）
   - 影响：CI 跑不动、push 阻塞、npm 装新包要切 npmmirror
   - 缓解：用 npmmirror、push 等网络恢复

2. **mypy 还没在本地跑过**（C 盘满装不上）
   - 影响：CI 端会跑，可能挂
   - 缓解：等阶段 5 配正式 CI 测试套件时一起解决

3. ~~**celery worker 还没起**~~ ✅ **已解决（2026-06-26）**
   - compose 加了 `celery-worker` 服务，上传后异步处理到 READY

4. **PostgreSQL RLS 没开**（只应用层过滤）
   - 影响：DB 直接查能跨租户看到数据
   - 风险等级：中（应用层已经过滤，但 SQL 注入时会漏）
   - 缓解：阶段 6 安全审计时加

5. **alembic 没配**（用 init_db.py 凑合）
   - 影响：生产环境没迁移工具
   - 缓解：阶段 5 引入

6. ~~**embedding API key 还没配**~~ ✅ **已解决（2026-06-26）**
   - 改用阿里千问（DashScope OpenAI 兼容）：`text-embedding-v2`（1536 维，与表结构对齐）+ `qwen-plus`
   - ⚠️ key 已填进 `.env` 和 `docker-compose.dev.yml`（明文）；接手时曾在终端回显过一次，建议轮换

7. **worker 开了 SQL echo**（`echo=settings.debug`，开发期 DEBUG=true 时日志刷屏）
   - 影响：仅开发期日志噪音，生产 DEBUG=false 自动关闭
   - 缓解：生产环境确保 DEBUG=false 即可

### ⚠️ 架构层面

1. **MinIO 没用，本地落盘**（多实例部署会数据不一致）
   - 解决：阶段 3 末尾或阶段 4 切 MinIO

2. **前端没写测试**（vitest 配了但 utils.test.ts 是占位）
   - 解决：阶段 6 前补关键组件测试

3. **没有审计日志**（谁改了什么不知道）
   - 解决：V1.5 计划

4. **没有速率限制**（接口可被刷）
   - 解决：阶段 6 配 slowapi 之类

5. **没有监控告警**（Sentry/Prometheus 配了但告警规则没写）
   - 解决：阶段 6 联调时补

6. **生成端点同步阻塞 30-90 秒**（`POST /articles/{id}/generate` 等四阶段 LLM 全跑完才返回）
   - 影响：客户端超时、用户体验差（无进度反馈）
   - 计划：V1.5 改 SSE 流式输出（先大纲即时返回，正文逐节推）
   - 临时缓解：前端加 loading 提示 + "正在生成，请耐心等待"

7. **生成接口无限流**（一个 MEMBER 可以无限并发触发生成，烧 token）
   - 影响：恶意/误操作可快速烧完 API 额度
   - 计划：阶段 6 配 slowapi（限 1 次/分钟/用户）

---

## 附录 A：常用命令速查

```bash
# === 容器管理 ===
docker ps                              # 列出运行中容器
docker logs -f fnai-backend-dev       # 实时日志
docker restart fnai-backend-dev       # 重启后端
docker exec -it fnai-backend-dev bash  # 进 shell

# === 数据库 ===
docker exec fnai-postgres psql -U fnai -d fnai_dev
# SQL: \dt 列表 / \d <table> 看表结构 / SELECT * FROM <table> LIMIT 5;

# === 后端测试 ===
cd backend
python -m scripts.test_kb_e2e          # KB 上传 + Celery + 检索 全链路 E2E

# === 前端 ===
cd frontend
npx tsc --noEmit                      # 类型检查
npx eslint src --max-warnings 0       # ESLint
npx prettier --check "src/**/*.{ts,tsx,css}"  # 格式检查
npm run build                         # 完整构建

# === 后端 lint ===
cd backend
ruff check .                          # ruff lint
ruff format --check .                 # ruff 格式
mypy app                              # mypy 类型

# === Git ===
git status
git log --oneline -10
git push origin main                  # 推送到远程
```

## 附录 B：测试账号

| 邮箱 | 密码 | 角色 |
|---|---|---|
| kbtest@example.com | test1234 | OWNER（测试 KB 上传用的） |
| sushu2@example.com | ? | OWNER（早期创建） |
| viewer@example.com | ? | VIEWER（测权限用） |

> 测试账号可能不全，看 `.workbuddy/memory/2026-06-18.md` 找创建历史。

## 附录 C：术语对照

| 业务术语 | 技术术语 | 备注 |
|---|---|---|
| 工作空间 | Tenant | 顶级隔离单位 |
| 成员 | TenantMember | 用户在某个工作空间的关系 |
| 角色 | Role | OWNER > ADMIN > MEMBER > VIEWER |
| 邀请 | Invitation | 用 token 一次性加入工作空间 |
| 知识库 | KnowledgeBase | 文档集合 |
| 文档 | Document | 上传的 PDF/Word 等 |
| 分片 | DocumentChunk | 切碎后的文本片段 + 向量 |
| 嵌入 | Embedding | 文本 → 1536 维向量 |
| RAG | Retrieval-Augmented Generation | 检索 + 生成 |

---

**最后更新**：2026-06-29 by AI Agent（接手）—— 阶段 4 全部完成（后端 5 表 + 模板 + CRUD + 四阶段生成 + 前端 TipTap 编辑器 + 文章管理页）
**预期下次更新**：阶段 5（发布与导出）启动后
