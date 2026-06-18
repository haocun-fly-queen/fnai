# FNAI V1 范围砍掉清单

> 目标：把当前架构的 14 阶段 / 42 表 / 33 周，砍成 4 个月能交付的「最小可商业闭环」
> 原则：**先验证商业，再做精细化**。能砍的都砍，不能砍的砍一半。
> 适用：7 人研发团队（3 后端 + 2 前端 + 2 AI/算法）

---

## 一、V1 必须留下的 4 件事（核心闭环）

### ✅ 1. 用户注册/登录 + 多租户
**为什么必须留？** 没有这个，平台不能商用。

**必须留的子项**
- 邮箱 + 密码注册（**可推迟**：手机号、SSO、OAuth）
- JWT 双 Token（access 15min + refresh 7d）
- 租户创建（**只做个人版**，团队版推迟）
- `tenant_id` 上下文注入（应用层 + RLS）
- 基础 RBAC（admin / member 两个角色够了）

**可推迟的子项**
- ❌ 实名认证、邀请码体系、扫码登录
- ❌ 细粒度权限（资源级别 RBAC）
- ❌ 审计日志（V1.5 再做）

---

### ✅ 2. 知识库 + 文档上传 + RAG
**为什么必须留？** 这是 GEO 平台差异化的核心。

**必须留的子项**
- 创建/删除知识库
- 上传 PDF / DOCX / Markdown / TXT
- 自动分块（chunk_size 500-1000，重叠 100）
- Embedding 入库（OpenAI text-embedding-3-small 即可）
- 检索接口（Top-K + 相似度阈值）
- 简单「来源高亮」返回

**可推迟的子项**
- ❌ 网页抓取（Firecrawl / Jina Reader）→ 推迟到 V1.5
- ❌ Notion / Confluence / 飞书集成 → 推迟到 V2
- ❌ 多模态（图片理解、表格抽取）→ 推迟到 V2
- ❌ 知识库版本管理 / 知识图谱 → 推迟到 V2
- ❌ 知识库协作（多人编辑、评论）→ 推迟到 V2

---

### ✅ 3. 文章生成（核心创作能力）
**为什么必须留？** 这是用户付费的「买点」。

**必须留的子项**
- 长文生成（基于知识库的 1500-3000 字文章）
- 段落级生成（按提纲分节生成）
- 标题 / 摘要生成
- 3-5 种**预设模板**（博客、产品介绍、新闻稿、SEO 文章、社交媒体）
- 编辑器（基础 Markdown 编辑器即可）
- 历史记录与版本保存

**可推迟的子项**
- ❌ GEO 优化（地理位置感知）→ 整个 P13 砍掉
- ❌ A/B 测试 → 整个 P10 砍掉
- ❌ 智能配图（AI 图片生成）→ 推迟到 V1.5
- ❌ 段落改写 / 续写 / 扩写 → 推迟到 V1.5
- ❌ 多语言生成 → 推迟到 V2
- ❌ 个性化风格学习（Few-shot 用户历史）→ 推迟到 V2

---

### ✅ 4. 简单的发布到外部站点
**为什么必须留？** 没有发布，文章生成就是个玩具。

**必须留的子项**
- 手动复制 Markdown 到剪贴板
- 一键导出 HTML
- **只做一个平台集成**：WordPress REST API（最常见）

**可推迟的子项**
- ❌ Shopify / Wix / Ghost / 微信公众号集成 → 推迟到 V1.5
- ❌ 自动定时发布 → 推迟到 V1.5
- ❌ 跨平台适配（不同平台格式转换）→ 推迟到 V1.5
- ❌ 发布回传数据采集 → 推迟到 V2

---

## 二、推迟到 V1.5（3-6 个月后）

| 模块 | 推迟内容 | 商业价值 | 技术复杂度 |
|------|----------|----------|------------|
| **P4 任务中心** | 完整任务看板、进度条、断点续传、SSE 实时推送 | 中 | 中 |
| **P5 内容工坊** | 模板市场、自定义模板、Prompt 调试器 | 中 | 中 |
| **P6 GEO 模块** | 地理位置、内容适配、地图集成 | 高 | 高 |
| **P8 SERP 监控** | 关键词排名追踪、竞品分析 | 高 | 中 |
| **P9 流量监控** | GA4 / GSC 集成、转化漏斗 | 中 | 中 |
| **P11 模型管理** | 完整模型配置页、成本看板、配额管理 | 中 | 低 |
| **P12 计费支付** | 完整计费引擎、订阅、发票、对账 | 高 | 高 |

> **V1.5 商业目标**：让客户能「用得爽」，从工具升级为工作流。

---

## 三、推迟到 V2（6-12 个月后）

| 模块 | 说明 |
|------|------|
| P7 多平台分发 | Shopify / Wix / 公众号 / 小红书 / 抖音 |
| P10 A/B 测试 | 内容实验、转化率优化 |
| P13 GEO 高级 | 地图集成、位置感知、多区域数据中心 |
| P14 平台治理 | 超级管理后台、租户管理、运营分析 |
| 完整 RAG 评估框架 | 召回率、答案质量、AB 实验 |
| 私有化部署 | 客户内网环境、离线模型 |
| 企业级安全 | 审计、SSO、SCIM、IP 白名单 |
| 多模态生成 | 图片、视频、音频 |
| 智能体（Agent）协作 | ContentGuard 升级为多 Agent 框架 |

---

## 四、必须砍的 42 张表（精简到 22 张）

### ✅ V1 必留（22 张）

#### 租户与用户（4 张）
1. `tenant`（租户）
2. `user`（用户）
3. `tenant_member`（租户-用户关系）
4. `role` / `permission`（**合并为 1 张** `role` + 字段，硬编码权限）

#### 知识库（4 张）
5. `knowledge_base`（知识库）
6. `document`（文档元数据）
7. `kb_chunk`（分块 + 向量）
8. `kb_upload_task`（上传任务记录）

#### 文章与生成（5 张）
9. `article`（文章）
10. `article_version`（版本快照）
11. `article_section`（段落，可选合并到 `article.content_json`）
12. `generation_task`（生成任务）
13. `prompt_template`（**简化版**，只存当前活跃版本）

#### 发布（2 张）
14. `publish_target`（发布目标，V1 只支持 WP）
15. `publish_log`（发布日志）

#### AI 与监控（4 张）
16. `model_call_log`（模型调用日志，**分区表**）
17. `embedding_cache`（embedding 缓存，避免重复调用）
18. `tenant_api_key`（租户自有 OpenAI Key，可选）
19. `usage_quota`（用量配额，V1 可简化为全局）

#### 系统（3 张）
20. `file_storage`（文件元数据）
21. `audit_log`（V1 可选，先不做）
22. `app_setting`（系统配置，KV 表）

### ❌ V1 砍掉的 20 张

| 砍掉的表 | 原因 | 何时再加 |
|----------|------|----------|
| `tenant_subscription` | 计费推迟 | V1.5 |
| `plan` / `pricing` | 计费推迟 | V1.5 |
| `invoice` / `payment` | 计费推迟 | V1.5 |
| `geo_location` / `geo_region` | GEO 模块推迟 | V2 |
| `serp_keyword` / `serp_ranking` | SERP 推迟 | V1.5 |
| `traffic_data` / `ga4_link` | 流量监控推迟 | V1.5 |
| `ab_test` / `ab_variant` | A/B 测试推迟 | V2 |
| `experiment_result` | A/B 测试推迟 | V2 |
| `comment` / `article_comment` | 协作功能推迟 | V2 |
| `notification` / `user_notification` | 通知推迟 | V1.5 |
| `webhook` / `webhook_event` | Webhook 推迟 | V1.5 |
| `tenant_invitation` | 邀请推迟 | V1.5 |
| `oauth_account` | OAuth 推迟 | V1.5 |
| `sso_config` | SSO 推迟 | V2 |
| `model_provider` / `model_config` | 模型管理推迟 | V1.5 |
| `template_market` | 模板市场推迟 | V1.5 |
| `image_asset` | AI 配图推迟 | V1.5 |
| `agent_message` / `agent_log` | Agent 详细日志合并到 `model_call_log` | V1.5 拆分 |
| `content_guard_result` | 合并到 `article.quality_score` | V1 |

---

## 五、API 接口精简（35 个 → 18 个）

### ✅ V1 必留

#### Auth（4 个）
1. `POST /api/v1/auth/register`
2. `POST /api/v1/auth/login`
3. `POST /api/v1/auth/refresh`
4. `POST /api/v1/auth/logout`

#### Tenant（2 个）
5. `GET /api/v1/tenant/me`
6. `PATCH /api/v1/tenant/me`

#### Knowledge Base（5 个）
7. `POST /api/v1/kb`（创建知识库）
8. `GET /api/v1/kb`（列表）
9. `DELETE /api/v1/kb/{id}`
10. `POST /api/v1/kb/{id}/documents`（上传）
11. `POST /api/v1/kb/{id}/search`（RAG 检索）

#### Article（5 个）
12. `POST /api/v1/articles`（创建 + 触发生成）
13. `GET /api/v1/articles`
14. `GET /api/v1/articles/{id}`
15. `PATCH /api/v1/articles/{id}`（编辑器保存）
16. `GET /api/v1/articles/{id}/versions`

#### Generation（1 个，简化）
17. `GET /api/v1/tasks/{id}`（统一任务状态查询）

#### Publish（1 个）
18. `POST /api/v1/articles/{id}/publish`

### ❌ 砍掉的接口

- ❌ 整个 `/api/v1/geo/*`（GEO 模块）
- ❌ 整个 `/api/v1/serp/*`（SERP 监控）
- ❌ 整个 `/api/v1/billing/*`（计费）
- ❌ 整个 `/api/v1/admin/*`（管理后台，V1 用 Django/Flask admin 凑合）
- ❌ 整个 `/api/v1/ab/*`（A/B 测试）
- ❌ `/api/v1/articles/{id}/collaborators`（协作）
- ❌ `/api/v1/templates/market`（模板市场）
- ❌ `/api/v1/models/*`（模型管理，简化为环境变量）

---

## 六、前端页面精简

### ✅ V1 必留（3 个页面 + 3 个子页）

```
登录注册页（共用）
    ↓
主控制台（Dashboard）
├── 知识库管理（KB 列表 + 文档上传）
├── 文章管理（文章列表 + 编辑器）
└── 账户设置（个人资料 + API Key）
```

### ❌ 砍掉的页面

- ❌ 超级管理后台 → 推迟到 V1.5
- ❌ GEO 工作台 → 推迟到 V2
- ❌ SERP 监控大盘 → 推迟到 V1.5
- ❌ 流量分析 → 推迟到 V1.5
- ❌ 模板市场 → 推迟到 V1.5
- ❌ 任务中心独立页 → 合并到 Dashboard
- ❌ 模型管理页 → 用环境变量配置
- ❌ 计费/订阅页 → 推迟到 V1.5

> **管理后台 V1 方案**：用 SQLAdmin / Django Admin 凑合，只给苏苏和运维用，不做 UI。

---

## 七、阶段重排（33 周 → 16 周）

### V1 阶段（16 周 / 4 个月）

| 周次 | 主题 | 关键交付 |
|------|------|----------|
| W1-2 | 基础设施 | Docker、CI/CD、数据库迁移、监控告警 |
| W3-4 | 认证与多租户 | 注册/登录、JWT、租户上下文 |
| W5-7 | 知识库 | 上传、分块、Embedding、检索 |
| W8-11 | 文章生成 | 模板、生成管线、编辑器 |
| W12-13 | 发布 | WordPress 集成、手动导出 |
| W14-15 | 联调与压测 | E2E 测试、性能优化 |
| W16 | 灰度发布 | 邀请内测、收集反馈 |

### V1.5 阶段（再 12 周 / 3 个月）

W17-28：补齐任务中心、内容工坊、模型管理、计费基础

### V2 阶段（再 24 周 / 6 个月）

W29-52：GEO、SERP、流量、A/B、多平台分发、多模态

---

## 八、团队分工建议（V1 阶段）

| 角色 | 人数 | V1 重点 |
|------|------|---------|
| **后端 A（主程）** | 1 | 架构、数据库、认证、API 规范 |
| **后端 B** | 1 | 知识库、RAG、Embedding |
| **后端 C** | 1 | 文章生成管线、Celery 任务、Prompt |
| **前端 A** | 1 | 主控制台、文章编辑器 |
| **前端 B** | 1 | 知识库管理、登录注册、账户设置 |
| **AI 算法 A** | 1 | Prompt 工程、Embedding 调优、生成质量 |
| **AI 算法 B** | 1 | RAG 召回优化、ContentGuard 基础版 |

> 砍掉 1 个后端 + 1 个前端工作量后，7 人在 16 周内完全能交付。

---

## 九、风险提示

| 风险 | 影响 | 缓解 |
|------|------|------|
| **砍功能导致客户不买账** | 商业失败 | V1 用「邀请内测」方式快速验证 5-10 个种子客户 |
| **技术债累积** | V1.5/V2 翻倍工作量 | 必须严守 CI + 审查清单，每周技术债会议 |
| **AI 质量不达标** | 产品口碑差 | V1 必须有 Prompt A/B + 简单评估，不达标不上线 |
| **多租户安全漏洞** | 法律风险 | 上线前必须做一次安全审计（SQL 注入、越权） |

---

## 十、给苏苏的执行 checklist

- [ ] 本周内：与产品/技术负责人过一遍这份清单，确认 V1 范围
- [ ] 本周内：在 `docs/decisions/0001-v1-scope.md` 写 ADR（架构决策记录）
- [ ] 下周：用「V1 必留表 / 必留接口 / 必留页面」反推分工
- [ ] 持续：每周 Review 一次范围变更请求，**任何新增都要砍掉同等工作量**

---

*砍范围不是为了少做事，是为了**做得对**。*

下一步要 (B) 配置文件（Pre-commit + CI）还是 (C) 代码审查 Checklist？
