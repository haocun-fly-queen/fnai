# FNAI 底层架构详解：多租户 · 认证 · 异步管线 · 向量检索

> 写给想深入理解这套系统的人。每一节都配**真实代码位置**和**为什么这么设计**。
> 阅读顺序建议：认证 → 多租户 → 异步管线 → 向量检索（后面依赖前面的概念）。
>
> 代码引用格式 `文件:行号`，可直接在编辑器里跳转。

---

## 目录

1. [认证（Authentication）：你是谁](#1-认证authentication你是谁)
2. [多租户隔离（Multi-tenancy）：你能看哪些数据](#2-多租户隔离multi-tenancy你能看哪些数据)
3. [异步任务管线（Celery）：耗时活儿怎么后台跑](#3-异步任务管线celery耗时活儿怎么后台跑)
4. [向量检索（pgvector RAG）：怎么按语义找内容](#4-向量检索pgvector-rag怎么按语义找内容)
5. [四者如何串成一条线](#5-四者如何串成一条线)

---

## 1. 认证（Authentication）：你是谁

### 1.1 核心思路：无状态 JWT 双 token

传统做法是"服务端存 session"，用户登录后服务器记一份"谁在线"。FNAI 不这么做，用的是 **JWT 无状态认证**：

- 登录成功 → 服务器签发一个 **token**（一串加密字符串）给前端
- 前端之后每次请求都在 HTTP 头带上 `Authorization: Bearer <token>`
- 服务器用密钥**验证** token，确认身份——**不查 session 表，不存任何状态**

> Java 对照：≈ Spring Security 的 JWT 模式，不是 HttpSession。

**为什么签两种 token**（`core/security.py:89-93`）：

| token | 寿命 | 用途 |
|---|---|---|
| `access_token` | 15 分钟 | 日常请求带它，短命——被偷了损失小 |
| `refresh_token` | 7 天 | 只用来换新的 access_token，长命但不直接当钥匙 |

### 1.2 密码怎么存：bcrypt 哈希

代码：`core/security.py:35-73`

用户密码**绝不明文存库**。注册时哈希成不可逆密文，登录时把输入的密码用同样算法哈希再比对。

```python
def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=12)              # 每次随机 salt
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")
```

**为什么用 bcrypt 不用 MD5/SHA256**（`security.py:28-31`）：
- **故意慢**：算一次约 100ms，暴力破解代价极高（MD5 一秒能算几亿次）
- **自带 salt**：每次哈希结果都不同，彩虹表攻击失效
- `rounds=12` 是 2026 年的安全基准，每 +1 慢一倍

一个安全细节（`security.py:65-73`）：`verify_password` 任何异常都返回 `False`，**不抛错也不区分"用户不存在"和"密码错"**——否则攻击者能用错误信息枚举出哪些邮箱注册过。

### 1.3 token 里装了什么

代码：`core/security.py:122-138`

JWT 的 payload（中间那段，**明文可解但有签名防篡改**）：

```python
payload = {
    "sub": user_id,            # subject：这个 token 代表谁
    "type": "access",          # 区分 access/refresh，防混用
    "iat": 签发时间戳,
    "exp": 过期时间戳,          # python-jose 自动校验过期
    "active_tenant_id": ...,   # 当前激活的租户（只 access token 有）
}
```

**关键安全约束**（`security.py:119-120`）：payload 是明文的，所以**绝不塞密码、邮箱、手机号**，只塞 `user_id` 和 `tenant_id` 这种"暴露了也没事"的标识。

`active_tenant_id` 是多租户的关键——它让 token 自己携带"这个请求该在哪个工作空间下处理"，下一节细讲。

### 1.4 每个请求怎么验身份

代码：`api/v1/deps.py:47-89` 的 `get_current_user`

这是"身份认证层"。任何需要登录的端点都 `Depends(get_current_user)`。流程：

1. 从 `Authorization` 头取出 token（`deps.py:66`，格式必须是 `Bearer xxx`）
2. `decode_token` 验签 + 验过期 + 验类型（`security.py:201-236`）
3. 从 token 的 `sub` 取出 `user_id`，**查 DB 确认用户还存在**（`deps.py:83`，用户可能被删了）
4. 任何一步失败 → 统一返回 **401**

> Java 对照：≈ 一个 `OncePerRequestFilter`，但 FastAPI 用 `Depends()` 函数式依赖注入表达（≈ Spring 的 `@Autowired`）。

一个易踩的坑（`deps.py:62-64`）：`get_current_user` 返回的 `User` 对象**包含 `hashed_password` 字段**，业务端点拿到后绝不能原样塞进响应，必须用 schema 序列化只挑安全字段。

### 1.5 token 续期

`access_token` 15 分钟就过期，难道用户每 15 分钟要重新登录？不是。前端在 access 过期时拿 `refresh_token` 调续期接口换新的 access——`refresh_token` 故意**不带租户信息**（`security.py:186-191`），因为它唯一用途就是换 token，暴露的业务上下文越少越安全。

---

## 2. 多租户隔离（Multi-tenancy）：你能看哪些数据

### 2.1 什么是多租户

FNAI 是 SaaS，一套系统服务很多家企业。每家企业是一个 **Tenant（租户/工作空间）**，数据必须**严格隔离**——A 公司绝不能看到 B 公司的知识库。

术语对照：

| 业务词 | 技术词 | 说明 |
|---|---|---|
| 工作空间 | Tenant | 顶级隔离单位 |
| 成员 | TenantMember | 用户在某工作空间的身份 |
| 角色 | Role | OWNER > ADMIN > MEMBER > VIEWER |

一个用户可以属于多个租户（在 A 公司是 OWNER，在 B 公司是 MEMBER），所以 `User` 和 `Tenant` 是**多对多**，中间表是 `TenantMember`（存 user_id + tenant_id + role）。

### 2.2 隔离方案：应用层过滤（不是数据库分库）

FNAI 用的是**共享数据库 + 共享表 + tenant_id 列**的方案：所有业务表都有 `tenant_id` 字段，每条查询都强制带 `WHERE tenant_id = ?`。

> 三种主流多租户方案：① 每租户一个库 ② 每租户一个 schema ③ 共享表加 tenant_id 列。FNAI 选 ③，最省运维、最容易上手，代价是隔离全靠应用层代码自觉（见 2.5 的风险）。

看 `services/knowledge.py:147-150` 的 `get_kb`，**每次查询都带 tenant_id**：

```python
stmt = select(KnowledgeBase).where(
    KnowledgeBase.id == kb_id,
    KnowledgeBase.tenant_id == tenant_id,   # ← 隔离线：不属于你的租户直接查不到
)
```

注意：跨租户访问不会报"403 禁止"，而是直接"404 不存在"——连"这个资源存在"都不告诉你，信息泄露更少。

### 2.3 token 怎么带租户：active_tenant_id

一个用户属于多个租户，那"当前这个请求"算在哪个租户名下？答案：**token 里的 `active_tenant_id`**。

- 登录时（`services/auth.py:149-152`）自动选一个默认租户（是 OWNER 的优先），签进 token
- 切换工作空间时，重新签发一个带新 `active_tenant_id` 的 token
- 业务请求进来，从 token 读出 `active_tenant_id`（`deps.py:131-149`），作为查询的过滤条件

### 2.4 RBAC：四级角色 + require_role 工厂

代码：`api/v1/deps.py:102-251`，**这是整个权限系统最精华的部分**。

角色是**等级制**，不是集合（`deps.py:102-107`）：

```python
_ROLE_HIERARCHY = {
    Role.OWNER: 4,   # 最高，能删租户/转让
    Role.ADMIN: 3,   # 团队管理
    Role.MEMBER: 2,  # 日常干活（上传/写/AI）
    Role.VIEWER: 1,  # 只读
}
```

权限检查用一个**工厂函数** `require_role(min_role)`，端点这样用：

```python
@router.post("/documents")
async def upload(
    membership: TenantMember = Depends(require_role(Role.MEMBER)),
):
    ...   # 进到这里说明：已登录 + 是当前租户成员 + 角色≥MEMBER
```

> Java 对照：≈ Spring Security 的 `@PreAuthorize("hasRole('MEMBER')")`。

**为什么是"工厂函数"**（`deps.py:155-159`）：普通依赖如 `get_current_user` 没参数，能直接当 `Depends` 用。但 `require_role(Role.ADMIN)` 要**带参数**，所以先调一次工厂，它返回内层的 `checker` 函数才是真正的依赖——这是 Python 闭包的经典用法（`deps.py:197` 的 `checker` 能"看见"外层的 `min_role`）。

`checker` 内部做三道检查（`deps.py:205-248`）：
1. token 里必须有 `active_tenant_id`，否则 400
2. **查 DB 确认 membership 还在**，否则 403
3. 角色等级 ≥ min_role，否则 403

### 2.5 最关键的安全设计：token 不可信，必须重查 DB

这是整套多租户最容易被忽视、也最重要的一点（`deps.py:126-128` 和 `216-218`）：

> token 里的 `active_tenant_id` **不能直接信任**。它只是"用户上次切换时记下的"，可能已经过期——用户可能**已被踢出该租户**，但他手里的 token 还没到 15 分钟过期。

所以 `require_role` 拿到 token 里的 tenant_id 后，**一定重新查 `TenantMember` 表确认成员关系还存在**（`deps.py:219-224`）。如果只信 token，被踢的人在 token 过期前还能继续操作——这是真实的越权漏洞。

记住这条原则：**token 用来"声明意图"，DB 用来"验证事实"。**

### 2.6 当前隔离的局限（已知技术债）

应用层过滤的软肋：**全靠每个查询都记得带 `tenant_id`**。哪天某个开发漏写一处 `WHERE tenant_id=?`，或者出现 SQL 注入，隔离就破了。

更彻底的方案是 PostgreSQL 的 **RLS（行级安全策略）**，在数据库层强制隔离，应用层就算漏了也兜得住。FNAI 目前**没开 RLS**（计划阶段 6 安全审计时加），所以现阶段隔离的可靠性取决于代码纪律——这也是为什么交接文档反复强调"永远加 tenant_id 过滤"。

---

<!-- SECTION3 -->

## 3. 异步任务管线（Celery）：耗时活儿怎么后台跑

### 3.1 为什么需要异步

用户上传一个 PDF，平台要做：解析全文 → 切成小段 → **每段调一次千问 API 算向量** → 写库。一个几十页的文档可能要几十秒甚至几分钟。

如果在 HTTP 请求里同步做完，用户的浏览器要转圈等几分钟，超时、体验崩坏。所以拆成两段：

```
用户上传 PDF
  ↓ FastAPI 立刻返回 201 + status=pending   ← HTTP 请求秒回
  ↓ 把"处理任务"丢进队列
  ↓ 独立的 worker 进程在后台慢慢做           ← 耗时活儿在这
  ↓ 做完把 status 改成 ready
用户轮询/刷新看到 ready
```

> Java 对照：≈ `@Async` 方法 + 消息队列（RabbitMQ/Kafka）的消费者。

### 3.2 三个角色：broker、worker、result backend

- **Broker（消息中转站）**：用 **Redis**。FastAPI 把任务投进来，worker 从这里取。代码 `workers/celery_app.py:31`，用 `redis://fnai-redis:6379/1`
- **Worker（干活的进程）**：独立的容器 `fnai-celery-dev`，专门消费任务。`docker-compose.dev.yml` 里单独起的服务
- **Result backend（结果存放）**：也是 Redis（`/2` 库），存任务执行结果

> 这三者通过 Redis 解耦：FastAPI 和 worker 是**两个独立进程**，甚至可以部署在不同机器上，互不阻塞。

### 3.3 Celery 实例配置

代码：`workers/celery_app.py`

```python
celery_app = Celery(
    "fnai",
    broker=settings.celery_broker_url,        # Redis db1
    backend=settings.celery_result_backend,   # Redis db2
    include=["app.workers.tasks"],            # 告诉 worker 去哪找任务
)
```

几个关键配置（`celery_app.py:43-57`）及**为什么**：

| 配置 | 值 | 为什么 |
|---|---|---|
| `task_acks_late` | True | 任务**执行完**才确认。worker 中途崩了，任务会被重新投递（at-least-once 保证不丢） |
| `worker_prefetch_multiplier` | 1 | 一次只取一个任务。长任务场景更公平，不会一个 worker 屯一堆 |
| `task_serializer` | json | 不用 pickle，避免反序列化安全风险 |
| `task_time_limit` | 600s | 硬超时，防任务卡死拖垮 worker |

### 3.4 核心任务：process_document

代码：`workers/tasks.py:30-130`

这是整条管线的心脏。`process_document(doc_id)` 串起 4 个步骤：

```
读原始文件 → parser 解析成纯文本 → chunker 切分 → embedding 向量化 → 写 chunks
```

**状态机**（`tasks.py:48-50`）：

```
PENDING → PROCESSING → READY
                  ↘ FAILED（记 error_message）
```

任务一开始把文档置 `PROCESSING`，成功置 `READY`，任何异常置 `FAILED` 并记下原因——前端就能显示"处理失败：xxx"。

### 3.5 worker 为什么用同步数据库连接

这是个**非显而易见的关键决策**（`db/session.py` 的 `sync_session_scope`）。

主应用（FastAPI）用的是 **async** 数据库连接（asyncpg）。但 Celery worker 是**同步进程模型**，在里面跑 asyncio 事件循环容易出 "event loop is closed"、连接跨循环复用等诡异 bug。

所以 worker 专门用一套**同步** SQLAlchemy 连接（psycopg2 驱动，走 `database_url_sync`）。代码里两套并存：
- `get_db` / `session_scope`：async，给 FastAPI 端点用
- `sync_session_scope`：sync，给 Celery 任务用

> 教训：**异步框架 + 同步任务队列混用时，DB 连接要分开**。强行让 Celery 跑 async 是常见的踩坑点。

### 3.6 三层容错设计

管线对失败做了三层防护：

1. **embedding API 层**（`services/embedding.py:111-130`）：调千问遇到限流(429)/超时，用 `tenacity` 指数退避重试 3 次（2s→4s→...）
2. **Celery 任务层**（`tasks.py:33-37`）：整个任务再加一层重试（`max_retries=2`），兜底网络抖动
3. **状态落库**（`tasks.py:124-130`）：失败时用**独立的新 session** 写 FAILED 状态，避免和出错的 session 搅在一起导致状态写不进去

还有**幂等设计**（`tasks.py:106-110`）：重复处理同一个文档时，先删旧 chunks 再写，避免 `chunk_index` 唯一约束冲突。已经 READY 的文档直接跳过。

### 3.7 上传如何触发任务

代码：`services/knowledge.py` 的 `upload_document` 末尾

文件落盘成功后：

```python
from app.workers.tasks import process_document
process_document.delay(str(doc_id))   # .delay() = 投递到队列，立即返回
```

`.delay()` 是 Celery 的投递语法，把任务塞进 Redis 队列就立刻返回，不等执行。一个细节：投递失败（比如 Redis 挂了）**只记日志不让上传失败**——文档已落盘，可以稍后重新触发，不能因为队列问题让用户上传白费。

---

<!-- SECTION4 -->

## 4. 向量检索（pgvector RAG）：怎么按语义找内容

### 4.1 问题：关键词搜索不够用

传统搜索是"关键词匹配"——你搜"怎么退货"，只能匹配到含"退货"两字的文档。但如果文档里写的是"商品退换流程"，关键词搜索就漏了。

**语义检索**解决这个：把文本变成"意思的数学表示"，按**意思相近**而非字面相同来找。"退货"和"退换流程"在语义空间里距离很近，就能被召回。

> 这是 RAG（检索增强生成）的"检索"部分——给 LLM 喂"相关的企业资料"，让它基于真实资料答题，而不是瞎编。

### 4.2 核心：embedding 向量

**embedding** 就是把一段文本变成一个定长的浮点数组（FNAI 用 **1536 维**）。语义相近的文本，向量在空间里也相近。

- 谁来算：千问的 `text-embedding-v2` 模型（`services/embedding.py`）
- 为什么是 1536 维：模型输出就是 1536，且数据库表的向量列写死了 `vector(1536)`，必须对齐

### 4.3 向量怎么存：pgvector

代码：`models/document_chunk.py:128-134`

FNAI 没有单独上专门的向量数据库（Pinecone/Milvus），而是用 PostgreSQL 的 **pgvector 扩展**——**一个数据库同时存业务数据和向量**，少维护一个组件。

```python
embedding = mapped_column(
    Vector(EMBEDDING_DIM),   # pgvector 的向量列，1536 维
    nullable=True,           # 处理中还没算出来时为 NULL
)
```

每个 `DocumentChunk`（文档切出来的一小段）存：原文 `content` + 位置 `char_start/char_end` + 向量 `embedding`。位置信息让检索命中后能**跳回原文定位**。

### 4.4 ivfflat 索引：让向量搜索快起来

代码：`models/document_chunk.py:179-186`

百万级向量逐个算距离太慢，pgvector 提供 **ivfflat 索引**加速：

```python
Index(
    "ix_document_chunks_embedding",
    "embedding",
    postgresql_using="ivfflat",
    postgresql_with={"lists": 100},                    # 聚成 100 个簇
    postgresql_ops={"embedding": "vector_cosine_ops"}, # 用余弦距离
    postgresql_where=embedding.isnot(None),            # 只给非空向量建索引
)
```

> 原理：ivfflat 把向量预先聚成 100 个簇，查询时只在最近的几个簇里找，而不是全表扫描。`lists=100` 适合 10万~100万行的量级。

### 4.5 检索怎么查：cosine 距离

代码：`services/knowledge.py` 的 `search_chunks`

检索三步：

**① 把查询文本向量化**（`knowledge.py` 检索函数中段）

```python
vectors = await asyncio.to_thread(embedding.embed_texts, [query])
query_vec = vectors[0]
```

注意 `asyncio.to_thread`：`embed_texts` 是**同步函数**（给 Celery 用的），但检索 service 是 **async**。直接调会阻塞事件循环，所以丢到线程池跑。这是 async/sync 混用的标准处理手法。

**② 用 cosine_distance 排序取 Top-K**

```python
distance = DocumentChunk.embedding.cosine_distance(query_vec)
stmt = (
    select(..., distance.label("distance"))
    .join(Document, Document.id == DocumentChunk.document_id)  # join 拿来源文件名
    .where(
        DocumentChunk.tenant_id == tenant_id,         # ← 多租户隔离（又出现了！）
        DocumentChunk.knowledge_base_id == kb_id,
        Document.status == DocumentStatus.READY,       # 只搜处理完的文档
    )
    .order_by(distance.asc())                          # 距离越小越相似
    .limit(top_k)
)
```

**③ 转成相似度分数 + 可选阈值过滤**

```python
score = 1.0 - float(row.distance)        # cosine 距离 → 相似度（越大越像）
if min_score is not None and score < min_score:
    continue                              # 过滤掉勉强沾边的结果
```

### 4.6 三个值得注意的设计

1. **余弦距离 vs 相似度**：pgvector 返回的是"距离"（越小越近），对外暴露成"相似度 score = 1 - 距离"（越大越像），更符合直觉。
2. **只搜 READY 文档**：PENDING/FAILED 文档的内容不可信，不参与召回。
3. **多租户隔离贯穿到底**：检索查询同样带 `tenant_id` 过滤——向量检索绝不会跨租户串数据。这呼应了第 2 节："每个查询都带 tenant_id"是铁律。

---

## 5. 四者如何串成一条线

把前面四块拼起来，看一次完整的"上传资料 → 检索"全流程，每一环用到哪个底层：

```
┌─ 用户登录 ────────────────────────────────────────────┐
│  认证(§1)：bcrypt 验密码 → 签发带 active_tenant_id 的 JWT │
└───────────────────────────────────────────────────────┘
              ↓ 前端每次请求带 Bearer token
┌─ 上传 PDF 到知识库 ───────────────────────────────────┐
│  认证(§1)：get_current_user 验 token → 拿到 user        │
│  多租户(§2)：require_role(MEMBER) 查 DB 验成员+角色      │
│  → 文件落盘，写 Document(status=PENDING)                │
│  异步(§3)：process_document.delay() 投递任务，HTTP 秒回  │
└───────────────────────────────────────────────────────┘
              ↓ 后台 worker 进程
┌─ Celery 处理 ─────────────────────────────────────────┐
│  异步(§3)：parser 解析 → chunker 切分                    │
│  向量(§4)：千问算 embedding(1536维)                      │
│  → 写 DocumentChunk(带向量)，status=READY               │
└───────────────────────────────────────────────────────┘
              ↓ 用户发起检索
┌─ 语义检索 ────────────────────────────────────────────┐
│  认证(§1)：验 token                                     │
│  多租户(§2)：require_role(VIEWER) + 查询带 tenant_id     │
│  向量(§4)：query 向量化 → pgvector cosine 距离 Top-K     │
│  → 返回最相关的 chunks + 来源文件 + 相似度               │
└───────────────────────────────────────────────────────┘
```

**贯穿全程的两条主线**：

1. **每个入口都先过认证 + 权限**（§1 + §2）——没有 token 进不来，不是成员/角色不够也进不来。
2. **每个数据操作都带 tenant_id**（§2）——上传、处理、检索，无一例外。这是多租户 SaaS 的生命线。

而异步管线（§3）和向量检索（§4）是 RAG 的两个引擎：一个负责"把资料嚼碎入库"，一个负责"按意思找回来"。

---

## 附：想动手验证，从哪看起

| 想理解 | 读这个文件 | 跑这个 |
|---|---|---|
| 认证 + 权限 | `api/v1/deps.py`（最精华） | Swagger 登录后看 token |
| 多租户隔离 | `services/knowledge.py` 的 `get_kb` | 用两个账号试跨租户访问 → 404 |
| 异步管线 | `workers/tasks.py` | `docker logs -f fnai-celery-dev` 看处理过程 |
| 向量检索 | `services/knowledge.py` 的 `search_chunks` | `POST /knowledge/{id}/search` |
| 全链路 | — | `docker exec fnai-backend-dev python -m scripts.test_kb_e2e` |

> 端到端脚本 `scripts/test_kb_e2e.py` 把这四块全跑一遍，是最快的"活文档"。

---

*文档基于 2026-06-26 的代码状态。代码行号可能随迭代变化，以实际文件为准。*
