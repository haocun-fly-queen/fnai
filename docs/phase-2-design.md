# FNAI 第二阶段技术设计方案

**版本**: v1.1  
**日期**: 2026-07-10  
**目标**: 扩展文本类型、扩展发布平台、增强辅助功能  
**已确认决策**:  
- 结构化输出 → JSON Schema 约束(千问 JSON mode)  
- 知乎接入 → Cookie 方案(非 OAuth,类似微博)  
- 定时发布 → Celery Beat 轮询(每分钟,1分钟延迟可接受)

---

## 一、背景与目标

第一阶段(阶段 5)已完成核心闭环:

- 知识库上传 → 向量化 → 检索
- 基于 KB 生成文章(5 种模板:blog/product/news/seo/social)
- 发布到 WordPress / 微信公众号 / 微博 / Webhook
- 阶段 6 完成安全加固(多进程锁/SSRF/图片/加密)

第二阶段聚焦**横向扩展**:

1. **更多文本类型** — 垂直场景模板(电商/技术文档/营销文案) + 结构化输出(表格/列表)
2. **更多发布平台** — 知乎、Medium、今日头条等
3. **辅助功能增强** — 按文件选择生成、批量生成、定时发布、质量检查

---

## 二、架构重构:发布系统插件化(优先级最高)

### 问题

当前每个平台是一个独立的 service 文件(`wechat_mp.py` / `weibo.py`)+ 独立的端点文件 + `publish.py` 里硬编码的 `if type == "WORDPRESS"` 分支。每加一个平台要改 3-4 处,代码重复度高、难维护。

### 方案:插件注册机制

**核心抽象** — `BasePublisher` 基类:

```python
# app/services/publishers/base.py
from abc import ABC, abstractmethod
from typing import Any

class PublishResult:
    success: bool
    remote_id: str | None
    message: str
    metadata: dict[str, Any] = {}

class BasePublisher(ABC):
    """发布平台插件基类。每个平台实现一个子类并注册到 registry。"""
    
    @abstractmethod
    async def validate_config(self, config: dict) -> None:
        """验证配置有效性(创建/更新发布目标时调用)。
        
        抛 ValueError 如果配置无效(缺字段、URL 不安全等)。
        """
    
    @abstractmethod
    async def publish(
        self, 
        article: Article, 
        config: dict,
        options: dict,  # 平台特定选项(如微信的 author/digest、WordPress 的 status)
    ) -> PublishResult:
        """发布一篇文章到该平台。
        
        Args:
            article: 文章对象(已解密 KB、已 refresh)
            config: 发布目标配置(decrypt_config 后的明文)
            options: 本次发布的平台特定参数
        
        Returns:
            PublishResult: success/remote_id/message
        """
    
    @abstractmethod
    def get_config_schema(self) -> dict:
        """返回该平台配置的 JSON Schema(前端渲染表单用)。"""
    
    @abstractmethod
    def get_publish_options_schema(self) -> dict:
        """返回发布选项的 JSON Schema(如微信的 author/digest)。"""
```

**注册中心**:

```python
# app/services/publishers/registry.py
_PUBLISHERS: dict[PublishTargetType, BasePublisher] = {}

def register_publisher(platform_type: PublishTargetType, publisher: BasePublisher):
    _PUBLISHERS[platform_type] = publisher

def get_publisher(platform_type: PublishTargetType) -> BasePublisher:
    if platform_type not in _PUBLISHERS:
        raise ValueError(f"未注册的发布平台: {platform_type}")
    return _PUBLISHERS[platform_type]
```

**各平台插件**:

```python
# app/services/publishers/wordpress.py
class WordPressPublisher(BasePublisher):
    async def validate_config(self, config):
        # URL 安全性校验(复用现有 validate_wordpress_url)
        ...
    
    async def publish(self, article, config, options):
        client = WordPressClient(...)
        # 复用现有 _publish_to_wordpress 逻辑
        ...
        return PublishResult(success=True, remote_id=str(post_id), ...)
    
    def get_config_schema(self):
        return {"properties": {"site_url": ..., "username": ..., "app_password": ...}}

# 注册
register_publisher(PublishTargetType.WORDPRESS, WordPressPublisher())
```

**统一发布入口**:

`publish.py` 的 `publish_article` 端点改成:

```python
publisher = get_publisher(target.type)
result = await publisher.publish(article, decrypt_config(...), options)
```

### 收益

- 加新平台只需写一个 `XxxPublisher` 类 + 注册一行,不改 `publish.py`
- 配置校验、发布逻辑、Schema 定义都内聚在插件里
- 前端可动态拉 Schema 渲染表单(未来可扩展)

### 工作量

- 抽象基类 + 注册中心:0.5d
- 重构现有 4 个平台(WordPress/微信/微博/Webhook):2d
- 测试(确保重构后行为不变):1d
- **小计:3.5d**

---

## 三、按文件选择生成 + 批量生成

### 需求

1. 单篇生成可选知识库里的**部分文件**(而非整库)
2. **一次生成多篇**文章
3. 多篇里**每篇独立选文件**

### 数据模型

`articles` 表新增一列:

```sql
ALTER TABLE articles ADD COLUMN source_document_ids JSONB NULL;
COMMENT ON COLUMN articles.source_document_ids IS '选定的知识库文件 ID 列表;null/空=用整个 KB';
```

三态语义(向后兼容):

| knowledge_base_id | source_document_ids | 行为 |
|---|---|
| null | — | 不用知识库,纯模板生成(现状) |
| 有值 | null / 空 | 用**整个 KB**(现状,老文章不受影响) |
| 有值 | 有值 | 只用**这些文件**检索 |

### 检索层改动

`search_chunks` 加可选参数:

```python
async def search_chunks(
    ..., 
    document_ids: list[UUID] | None = None,  # 新增
):
    stmt = ...
    if document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))
```

`generation.py` 的 `_retrieve_context` 透传 `article.source_document_ids`。

### 批量生成

**执行方式**:Celery 后台任务(基础设施已完备)。

```
POST /articles/batch-generate   (MEMBER+)
  body: { 
    items: [  # 1-20 篇
      {title, topic, template_code, knowledge_base_id, 
       source_document_ids, target_word_count}, 
      ...
    ] 
  }
  ↓ 同步:校验 → 创建 N 篇 Article(DRAFT) → 投递 N 个 Celery 任务
  ↓ 立即返回: { article_ids: [...] }

前端轮询 GET /articles/{id} 看各篇 status
```

**新增 Celery 任务**:

```python
# app/workers/tasks.py
@celery_app.task(bind=True, max_retries=2)
def generate_article_task(self, article_id: str):
    """后台生成一篇文章(照搬 process_document 的同步范式)。"""
    try:
        with sync_session_scope() as db:
            article = db.get(Article, UUID(article_id))
            # 用 asyncio.run() 复用现有 async generate_article
            asyncio.run(generation_service.generate_article(...))
    except Exception as exc:
        # 失败标记 FAILED,不影响其他篇
        _mark_generation_failed(article_id, str(exc))
```

**决策**(已确认):

- 单篇生成保留同步(即时返回),批量走异步 → 维护两条链路
- 批量并发度:串行逐篇(worker `prefetch=1` 天然串行,不触发千问限流)
- 单批上限:20 篇

### 前端

1. KB 选完拉文件列表,多选框勾选(不选=整库)
2. 批量:可增删的"文章行"列表,每行独立配置
3. 进度:N 张卡片轮询状态

### 工作量

- 数据模型 + 迁移:0.5d
- 检索层改动:0.5d
- 单篇接入 `source_document_ids`:0.5d
- Celery 任务 + 批量端点:1.5d
- 前端(文件多选 + 批量表单 + 进度轮询):2-3d
- 测试:1d
- **小计:6-7d**

### 实施记录(2026-07-10)

**已完成项:**

| 步骤 | 状态 | 改动文件 | 说明 |
|------|------|---------|------|
| Alembic 迁移框架 | ✅ | `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako` | 异步引擎(asyncpg),baseline migration |
| 数据模型变更 | ✅ | `models/article.py`, `models/publish_log.py`, `models/prompt_template.py` | 加 6 列 +1 索引,migration `20b206af0b94` |
| 发布系统插件化 | ✅ | `services/publishers/{base,registry,wordpress,webhook,wechat_mp,weibo}.py` | BasePublisher 基类 +4 平台插件 +registry |
| publish.py 重构 | ✅ | `api/v1/publish.py` | 统一入口改为 registry 分发 |
| 检索层文件过滤 | ✅ | `services/knowledge.py`, `services/generation.py` | `search_chunks` 加 `document_ids` 参数 |
| 单篇接入 source_document_ids | ✅ | `services/article.py`, `api/v1/endpoints/article.py` | `create_article` 透传新字段 |
| 批量生成 API | ✅ | `workers/tasks.py`, `schemas/article.py`, `api/v1/endpoints/article.py` | Celery 任务 + `POST /articles/batch-generate` 端点 |

**关键实现细节:**

1. **Celery 任务用 async session**: `generate_article_task` 不能用 `sync_session_scope`(传给 async 函数会报错),改为 `asyncio.run()` 包裹整个异步逻辑,内部用 `session_scope()`(async 版本)。

2. **UUID 序列化**: `source_document_ids` 存 JSONB 时,UUID 对象不能直接序列化,需先 `[str(uid) for uid in source_document_ids]` 转字符串。

3. **Schema/Model 枚举不一致**: `schemas/publish.py` 的 `PublishTargetType` 用小写(`wordpress`),`models/publish_target.py` 用大写(`WORDPRESS`)。`_validate_publish_target_config` 加了 `_to_model_enum()` 做转换。

**已知问题(非阻塞):**

- `generation.py` 的 quality 阶段缺少 `import re`,导致 quality 步骤报 `NameError`。文章内容已生成但 status 标记为 FAILED。需补 `import re`。
- 发布目标 CRUD 的 schema 枚举值与 model 枚举值不一致(已有问题,非本次引入)。

---

## 四、文本类型扩展

### 需求

增加 3-5 个垂直场景模板 + 支持结构化输出(表格/列表)。

### 新增模板(预置系统模板)

| code | name | 场景 | 特点 |
|---|---|---|
| ecommerce | 电商产品描述 | 商品详情页 | 强调卖点、痛点、使用场景,带购买引导 |
| tech_doc | 技术文档 | API 文档、使用指南 | 准确、逻辑清晰、带代码示例 |
| marketing | 营销文案 | 广告、落地页 | 情感化、转化导向、FOMO/紧迫感 |
| comparison | 对比评测 | 产品对比、技术选型 | 多维度对比表、优缺点并陈 |
| tutorial | 教程指南 | 教学、操作步骤 | 分步骤、带示例、循序渐进 |

### 结构化输出(已确认:JSON Schema 约束)

**方案:千问 JSON mode + JSON Schema 约束**

利用千问的 `response_format: { type: "json_object" }` 强制输出结构化内容。

**大纲阶段改动**:

```python
# services/generation.py — _stage_outline
OUTLINE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "heading": {"type": "string"},
                    "content_type": {
                        "type": "string",
                        "enum": ["text", "table", "list"]
                    },
                    "table_columns": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "key_points": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["heading", "content_type"],
            },
        },
    },
    "required": ["title", "sections"],
}

# 调用时传 response_format
result = await _call_llm(
    ...,
    response_format={"type": "json_object", "schema": OUTLINE_SCHEMA},
)
```

**Section 阶段改动**:

根据 `content_type` 给不同的 section prompt:

- `text` → 现有行为(普通段落)
- `table` → "请生成一个 Markdown 表格,包含以下列:{table_columns}"
- `list` → "请生成带序号/要点的步骤列表"

```python
for sec in outline["sections"]:
    ct = sec.get("content_type", "text")
    if ct == "table":
        prompt = tpl.table_section_prompt.format(
            columns=", ".join(sec.get("table_columns", [])),
            heading=sec["heading"],
            context=context,
        )
    elif ct == "list":
        prompt = tpl.list_section_prompt.format(
            heading=sec["heading"],
            key_points=", ".join(sec.get("key_points", [])),
            context=context,
        )
    else:
        prompt = tpl.section_prompt.format(...)  # 现有行为
```

**LLM 层改动**:

`services/llm.py` 的 `chat()` 函数支持 `response_format` 参数,透传给千问 API:

```python
def chat(system_prompt, user_prompt, temperature=0.7, response_format=None, ...):
    kwargs = {...}
    if response_format:
        kwargs["response_format"] = response_format
    resp = client.chat.completions.create(**kwargs)
    ...
```

**改动范围**:

- `services/llm.py`: 支持 `response_format` 参数(0.5d)
- `services/generation.py`: outline/schema + section 按类型分发(1d)
- `models/prompt_template.py`: 新增 `table_section_prompt` 和 `list_section_prompt` 字段(0.5d)
- 模板编写: 3-5 个垂直模板的 4+2 套 prompt(需运营协作)

### 模板制作

每个模板需要 4 套 prompt(outline/section/seo/quality)。由产品/运营提供模板文案 → 开发写入 `prompt_templates` 表(或 seed 脚本)。

### 工作量

- 设计 + 编写 3-5 个模板的 4 套 prompt:2-3d(需运营协作)
- Schema 约束 + 结构化输出支持:1.5d
- 测试(生成质量评估):1d
- **小计:4.5-5.5d**

---

## 五、平台扩展:知乎 + Medium

### 知乎

**接入方式**:Cookie 方案(OAuth 企业资质审核难度大,改用类似微博的 Cookie 方式)。

**配置**:

```python
{
    "cookie": "...",  # 加密,用户从浏览器复制知乎 Cookie
}
```

**发布流程**:

1. 用户手动复制知乎网页版 Cookie(F12 → Network → 复制 Cookie 请求头)
2. 填到发布目标配置
3. 后端用 Cookie 模拟 HTTP 请求创建文章(非官方 API,但稳定)

**插件实现**:

```python
class ZhihuPublisher(BasePublisher):
    async def publish(self, article, config, options):
        headers = {"Cookie": config["cookie"]}
        # 图片处理:上传到知乎图床,替换 src
        content = await self._process_images(article.content)
        # POST 到知乎草稿箱创建接口(需抓包获取真实端点)
        payload = {"title": article.title, "content": content, ...}
        resp = await httpx.post(
            "https://zhuanlan.zhihu.com/api/articles/drafts",
            json=payload, headers=headers,
        )
        draft_id = resp.json()["id"]
        # 发布草稿
        await httpx.post(f".../{draft_id}/publish", headers=headers)
        return PublishResult(success=True, remote_id=draft_id, ...)
```

**注意**:

- 知乎限制标题 50 字、正文 10 万字
- 图片需上传知乎图床(复用阶段 6 的 `image_processor`)
- Cookie 有效期约 30 天,过期需用户重新填(前端可提示)
- 需要抓包确认知乎草稿箱/发布接口的真实端点和参数格式

### Medium

**接入方式**:Medium API(需 Integration Token,用户在 Medium 后台生成)。

**配置**:

```python
{
    "integration_token": "...",  # 加密
    "author_id": "...",          # 用户 ID(token 对应的作者)
}
```

**发布流程**:

```python
class MediumPublisher(BasePublisher):
    async def publish(self, article, config, options):
        headers = {"Authorization": f"Bearer {config['integration_token']}"}
        # Medium 只支持 Markdown/HTML
        payload = {
            "title": article.title,
            "content": article.content,
            "contentFormat": "markdown",
            "publishStatus": options.get("publish_status", "draft"),  # draft/public
        }
        resp = await httpx.post(
            f"https://api.medium.com/v1/users/{config['author_id']}/posts",
            json=payload, headers=headers,
        )
        return PublishResult(success=True, remote_id=resp.json()["data"]["id"], ...)
```

**注意**:

- Medium 图片不需额外上传(直接 markdown `![](url)` 即可,Medium 会拉取)
- API 限流:每小时 60 次(单租户够用,多租户需考虑 rate limit)

### 工作量(2 个平台)

- 知乎插件(含 OAuth + token 刷新 + 图床):2d
- Medium 插件:1d
- 测试:1d
- **小计:4d**

---

## 六、辅助功能

### 6.1 定时发布(已确认:Celery Beat 轮询)

**需求**:创建文章时指定 `scheduled_at`,到时自动发布到选定平台。

**方案**:Celery Beat 轮询(每分钟扫表,最多 1 分钟延迟,实现简单)。

```python
# app/workers/tasks.py
@celery_app.task
def check_scheduled_articles():
    """每分钟扫一次 scheduled_at <= now 且 status=completed 的文章,触发发布。"""
    with sync_session_scope() as db:
        now = datetime.utcnow()
        stmt = select(Article).where(
            Article.scheduled_at <= now,
            Article.scheduled_at.isnot(None),
            Article.status == ArticleStatus.COMPLETED,
            Article.is_published == False,  # 新增标志位
        )
        articles = db.execute(stmt).scalars().all()
        for article in articles:
            # 调发布端点或直接走发布逻辑
            publish_to_scheduled_targets(article)
            article.is_published = True
        db.commit()

# 注册到 Beat
celery_app.conf.beat_schedule = {
    "check-scheduled-articles": {
        "task": "app.workers.tasks.check_scheduled_articles",
        "schedule": 60.0,  # 每 60 秒
    },
}
```

**数据模型**:

- `articles.scheduled_at TIMESTAMPTZ NULL`
- `articles.is_published BOOLEAN DEFAULT FALSE`

**前端**:创建文章时加一个"定时发布"日期时间选择器。

**工作量**:1.5d(含 Beat 配置 + 测试)

### 6.2 批量发布

**需求**:选多篇文章,一次发布到同一个目标。

**实现**:

```
POST /articles/batch-publish
  body: { article_ids: [...], target_id: "..." }
  ↓ 投递 N 个 Celery 任务(复用单篇发布逻辑)
  ↓ 立即返回 { publish_log_ids: [...] }
```

**工作量**:0.5d(几乎是批量生成的平行复制)

### 6.3 质量检查增强

**需求**:生成后自动检查错别字、敏感词、可读性(句子过长、重复词等)。

**方案**:

- 错别字:调千问 API 的"纠错"功能(或本地 SymSpell 库)
- 敏感词:维护黑名单(政治/色情/暴力),正则匹配
- 可读性:统计平均句长、重复词比例,给出建议

**集成点**:quality 阶段后加一个 `_check_quality` 步骤,输出警告(不阻断生成)。

**工作量**:2d(含敏感词库维护)

### 6.4 发布效果追踪

**需求**:记录发布后的阅读量、点赞数等(如果平台 API 支持)。

**方案**:

- `publish_logs` 表新增 `metrics JSONB`(存 `{views, likes, comments, ...}`)
- 定时任务(Celery Beat)拉取各平台数据更新 metrics
- 前端展示趋势图

**注意**:不是所有平台都提供统计 API(微博有、Medium 没有),分平台实现。

**工作量**:3d(含定时拉取 + 前端图表)

---

## 七、实施计划与优先级

### 分 3 个子阶段(总计约 4-5 周)

#### 2A · 架构重构 + 知乎(约 2 周)

**目标**:打地基 + 接一个新平台验证插件化。

| 任务 | 工期 |
|---|
| 发布系统插件化重构 | 3.5d |
| 知乎插件(Cookie 方案 + 图床 + 抓包) | 1.5d |
| Medium 插件 | 1d |
| 测试(重构后回归 + 新平台) | 1.5d |
| **小计** | **7.5d / 1.5 周** |

#### 2B · 按文件生成 + 批量 + 文本扩展(约 2 周)

**目标**:核心生成能力提升。

| 任务 | 工期 |
|---|
| 按文件选择 + 批量生成 | 6-7d |
| LLM 层支持 response_format(JSON Schema) | 0.5d |
| generation.py: outline schema + section 按类型分发 | 1d |
| prompt_templates 表新增 table/list prompt 列 | 0.5d |
| 3-5 个垂直模板编写(需运营协作) | 2-3d |
| 结构化输出测试 | 1d |
| **小计** | **11-13d / 2.2-2.6 周** |

#### 2C · 辅助功能(约 1 周)

**目标**:定时发布 + 批量发布 + 质量检查。

| 任务 | 工期 |
|---|
| 定时发布(Celery Beat) | 1.5d |
| 批量发布 | 0.5d |
| 质量检查增强 | 2d |
| 发布效果追踪(可选) | 3d |
| **小计** | **4-7d / 0.8-1.4 周** |

### 优先级排序

**P0(必做,阻塞后续)**:

- 发布系统插件化重构(后续所有平台扩展依赖它)

**P1(核心价值)**:

- 按文件选择生成 + 批量生成(用户高频需求)
- 知乎 + Medium 接入(扩大平台覆盖)
- 新增 3 个以上垂直模板(差异化竞争力)

**P2(体验优化)**:

- 定时发布、批量发布
- 结构化输出(表格/列表)
- 质量检查增强

**P3(锦上添花)**:

- 发布效果追踪(需平台 API 支持,部分平台不可行)

### 建议执行顺序

1. **2A 先行** — 插件化重构是地基,必须最先做
2. **2B 并行拆分** — 按文件/批量生成和文本扩展可以两个人并行开发
3. **2C 收尾** — 辅助功能逐个迭代,可根据实际进度调整优先级

---

## 八、风险与依赖

### 技术风险

1. **知乎 Cookie 稳定性** — Cookie 有效期约 30 天,过期需用户重新填;非官方接口可能随知乎版本变化(需维护)
2. **千问 API 限流** — 批量生成 20 篇需控制并发,否则触发限流(已决策串行逐篇,规避)
3. **Celery worker 稳定性** — 长时间运行需监控(Flower + Sentry)

### 外部依赖

1. **运营协作** — 新模板的 prompt 需产品/运营提供文案(约 2-3 天)
2. **平台 API 文档** — 知乎/Medium API 可能更新,需保持关注
3. **前端开发** — 批量表单、进度轮询、文件多选需前端协同(约 3-4 天)

### 数据迁移

- `articles` 新增 `source_document_ids / scheduled_at / is_published` 列 — 需写 Alembic 迁移,可回滚
- 老文章自动兼容(新列默认 null)

---

## 九、验收标准

### 2A(插件化 + 知乎/Medium)

- [ ] 重构后现有 4 个平台(WordPress/微信/微博/Webhook)功能不变
- [ ] 加新平台只需写一个插件类 + 注册一行
- [ ] 知乎 Cookie 方案走通:填 Cookie → 发布文章 → 图片上传
- [ ] Medium 能用 Integration Token 发布文章

### 2B(按文件 + 批量 + 文本扩展)

- [ ] 单篇生成可选 KB 里的 1-N 个文件,生成内容只用选定文件的知识
- [ ] 批量生成 API 能一次提交 20 篇,各篇独立选文件
- [ ] 前端能轮询 N 篇进度,单篇失败不影响其他篇
- [ ] 新增至少 3 个垂直模板(电商/技术文档/营销),生成质量符合场景
- [ ] 结构化输出能生成 Markdown 表格和有序列表

### 2C(辅助功能)

- [ ] 定时发布:创建文章时设 `scheduled_at`,到时自动发布
- [ ] 批量发布:选多篇文章一次发布到同一目标
- [ ] 质量检查:生成后自动标记错别字/敏感词,给出可读性建议

---

## 十、后续迭代方向(V3)

- **自定义模板**(租户级):允许用户自己写 prompt 模板
- **流式生成**(SSE):前端实时看到生成进度,不用等 30-90 秒
- **A/B 测试**:同一主题生成多个版本,用户选最优
- **发布审批流**:企业版需要,生成后需审批才能发布
- **更多平台**:抖音、快手、小红书(视频平台需对接视频生成能力)

---

## 附录 A:新增数据模型变更

### articles 表

```sql
ALTER TABLE articles ADD COLUMN source_document_ids JSONB NULL;
ALTER TABLE articles ADD COLUMN scheduled_at TIMESTAMPTZ NULL;
ALTER TABLE articles ADD COLUMN is_published BOOLEAN DEFAULT FALSE;

CREATE INDEX ix_articles_scheduled ON articles(scheduled_at) 
  WHERE scheduled_at IS NOT NULL AND is_published = FALSE;
```

### publish_logs 表

```sql
ALTER TABLE publish_logs ADD COLUMN metrics JSONB NULL;
COMMENT ON COLUMN publish_logs.metrics IS '发布效果统计:阅读量/点赞数等';
```

### prompt_templates 表

新增 2 列(支持结构化输出):

```sql
ALTER TABLE prompt_templates ADD COLUMN table_section_prompt TEXT NOT NULL DEFAULT '';
ALTER TABLE prompt_templates ADD COLUMN list_section_prompt TEXT NOT NULL DEFAULT '';
COMMENT ON COLUMN prompt_templates.table_section_prompt IS '表格类型小节的 prompt(结构化输出)';
COMMENT ON COLUMN prompt_templates.list_section_prompt IS '列表类型小节的 prompt(结构化输出)';
```

新增 5 行系统模板(code: ecommerce / tech_doc / marketing / comparison / tutorial),每个 6 套 prompt(outline/section/seo/quality/table_section/list_section)。

---

## 附录 B:关键接口变更

### 新增端点

```
POST   /articles/batch-generate          批量生成(1-20 篇)
POST   /articles/batch-publish            批量发布
GET    /knowledge-bases/{id}/documents    列出 KB 的文件(前端文件选择用)
```

### 修改端点

```
POST   /articles                          新增 source_document_ids / scheduled_at 字段
POST   /articles/{id}/generate            支持 source_document_ids 参数
```

---

## 附录 C:Celery 配置增强

### Beat 调度(定时任务)

```python
# app/workers/celery_app.py
celery_app.conf.beat_schedule = {
    "check-scheduled-articles": {
        "task": "app.workers.tasks.check_scheduled_articles",
        "schedule": 60.0,
    },
    "update-publish-metrics": {  # 拉取发布效果统计
        "task": "app.workers.tasks.update_publish_metrics",
        "schedule": 3600.0,  # 每小时
    },
}
```

### 监控

推荐用 Flower(Celery 可视化监控):

```bash
celery -A app.workers.celery_app flower
# 访问 http://localhost:5555 查看任务队列/worker 状态
```

---

**文档结束**
