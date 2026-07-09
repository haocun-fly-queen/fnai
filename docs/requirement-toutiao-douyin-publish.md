# 头条号 & 抖音发布功能 — 需求文档

> 版本：V1
> 编写日期：2026-07-09

---

## 一、背景与目标

**背景：** FNAI 平台已支持发布到 WordPress、微信公众号、微博。现需扩展头条号和抖音两个平台，实现"AI 生成文章 → 一键发布"的完整闭环。

**目标：**
- 用户在 FNAI 平台生成文章后，可直接发布到头条号/抖音
- 发布过程可追踪（状态、错误信息）
- 配置管理简单（填入账号凭证即可）

---

## 二、功能需求

### 2.1 头条号发布

| 需求项 | 说明 |
|--------|------|
| **发布内容类型** | 图文文章（头条号支持文章发布） |
| **配置管理** | 用户填入 `client_key` + `client_secret`，系统通过 OAuth 获取 access_token |
| **发布流程** | 创建草稿 → 提交发布 → 轮询状态 |
| **必填参数** | 标题、正文（HTML）、封面图 |
| **可选参数** | 摘要、标签、分类 |
| **状态追踪** | PENDING → SUCCESS/FAILED |
| **错误处理** | token 过期自动刷新、发布失败重试、降级提示 |

### 2.2 抖音发布

| 需求项 | 说明 |
|--------|------|
| **发布内容类型** | 图文笔记（抖音支持图文内容，非仅视频） |
| **配置管理** | 用户填入 `client_key` + `client_secret`，OAuth 授权 |
| **发布流程** | 上传素材 → 创建内容 → 提交审核 |
| **必填参数** | 标题、正文、封面图 |
| **可选参数** | 话题标签、位置 |
| **状态追踪** | PENDING → SUCCESS/FAILED |
| **特殊限制** | 图文内容字数限制、图片数量限制 |

---

## 三、技术架构

### 3.1 现有架构模式

项目采用**独立端点模式**（参考微信/微博），每个平台有独立的：
- `services/{platform}.py` — API 客户端封装
- `api/v1/endpoints/{platform}.py` — HTTP 端点
- `schemas/{platform}.py` — 数据校验

**建议头条和抖音走独立端点模式**（API 较复杂，需要 OAuth）。

### 3.2 发布流程参考（微信公众号为例）

```
用户点击发布
  → PublishDialog 选择平台 Tab
  → 调用 publishToXxx({article_id, config_id, ...})
  → POST /api/v1/xxx/articles/{id}/publish-xxx
  → endpoint():
      1. 校验文章存在 + 内容非空
      2. 从 PublishTarget(type=XXX) 获取配置
      3. 创建 PublishLog (status=PENDING)
      4. 调用平台 API（带重试）
      5. 保存 remote_id
      6. 可选：群发/推送
  → 返回结果
```

### 3.3 需要新增/修改的文件

#### 后端

| 文件 | 操作 | 说明 |
|------|------|------|
| `models/publish_target.py` | 修改 | 枚举加 `TOUTIAO`、`DOUYIN` |
| `schemas/publish.py` | 修改 | 枚举加对应值 |
| `schemas/toutiao.py` | 新增 | 头条号请求/响应 Schema |
| `schemas/douyin.py` | 新增 | 抖音请求/响应 Schema |
| `services/toutiao.py` | 新增 | 头条号 API 客户端（OAuth + 发布 + 状态查询） |
| `services/douyin.py` | 新增 | 抖音 API 客户端 |
| `api/v1/endpoints/toutiao.py` | 新增 | 配置 CRUD + 发布 + 状态查询 |
| `api/v1/endpoints/douyin.py` | 新增 | 同上 |
| `api/v1/__init__.py` | 修改 | 注册新路由 |

#### 前端

| 文件 | 操作 | 说明 |
|------|------|------|
| `lib/publish-api.ts` | 修改 | 加头条/抖音类型 + API 函数 |
| `components/PublishDialog.tsx` | 修改 | 加 Tab + 表单 |
| `pages/ToutiaoConfigPage.tsx` | 新增 | 头条号配置管理页 |
| `pages/DouyinConfigPage.tsx` | 新增 | 抖音配置管理页 |
| `App.tsx` | 修改 | 注册新路由 |

### 3.4 数据库变更

需要执行 SQL（或 Alembic 迁移）：

```sql
-- 添加新的发布目标类型
ALTER TYPE publishtargettype ADD VALUE IF NOT EXISTS 'TOUTIAO';
ALTER TYPE publishtargettype ADD VALUE IF NOT EXISTS 'DOUYIN';
```

---

## 四、API 接口设计

### 4.1 头条号

| 接口 | 方法 | 说明 |
|------|------|------|
| `/toutiao/toutiao-configs` | POST | 创建头条号配置 |
| `/toutiao/toutiao-configs` | GET | 列出配置 |
| `/toutiao/toutiao-configs/{id}` | PUT | 更新配置 |
| `/toutiao/toutiao-configs/{id}` | DELETE | 删除配置 |
| `/toutiao/articles/{id}/publish-toutiao` | POST | 发布文章 |
| `/toutiao/publish-toutiao/status/{publish_id}` | GET | 查询状态 |

### 4.2 抖音

| 接口 | 方法 | 说明 |
|------|------|------|
| `/douyin/douyin-configs` | POST | 创建抖音配置 |
| `/douyin/douyin-configs` | GET | 列出配置 |
| `/douyin/douyin-configs/{id}` | PUT | 更新配置 |
| `/douyin/douyin-configs/{id}` | DELETE | 删除配置 |
| `/douyin/articles/{id}/publish-douyin` | POST | 发布内容 |
| `/douyin/publish-douyin/status/{publish_id}` | GET | 查询状态 |

---

## 五、各平台配置结构（config JSONB 字段）

| 平台 | config 结构 | 必填字段 |
|------|------------|---------|
| **头条号** | `{"client_key": "...", "client_secret": "...", "access_token": "...", "refresh_token": "..."}` | client_key, client_secret |
| **抖音** | `{"client_key": "...", "client_secret": "...", "access_token": "...", "refresh_token": "..."}` | client_key, client_secret |

---

## 六、前端 UI 设计

发布对话框扩展为多 Tab 模式：

```
┌─────────────────────────────────────────────────┐
│  发布文章                                         │
│  ┌────────┬────────┬────────┬────────┬────────┐  │
│  │WordPress│ 微信    │  微博   │ 头条号  │  抖音  │  │
│  └────────┴────────┴────────┴────────┴────────┘  │
│                                                   │
│  [根据选中 Tab 显示不同表单]                         │
│  - 头条号: 选账号 + 标题 + 摘要 + 标签 + 封面图       │
│  - 抖音: 选账号 + 标题 + 正文 + 话题标签 + 封面图     │
│                                                   │
│  [取消]  [发布]                                     │
└─────────────────────────────────────────────────┘
```

---

## 七、参考实现

让开发同事参考以下已实现的文件：

| 参考文件 | 用途 |
|---------|------|
| `services/wechat_mp.py` | OAuth + 重试机制 + 错误处理模式 |
| `api/v1/endpoints/wechat_mp.py` | 端点结构 + 错误翻译 + 降级处理 |
| `schemas/wechat.py` | Schema 定义模式 |
| `components/PublishDialog.tsx` | 前端 Tab 切换 + 表单交互 |
| `pages/WechatConfigPage.tsx` | 配置管理页 UI |

---

## 八、注意事项

| 项 | 说明 |
|----|------|
| **OAuth 流程** | 头条和抖音都用字节跳动统一的 OAuth 2.0，需引导用户授权 |
| **access_token 刷新** | 参考微信的 token 缓存 + 自动刷新机制 |
| **图片要求** | 封面图需要上传到对应平台的素材库（不能用外部 URL） |
| **内容格式** | 需要 HTML → 平台特定格式的转换（参考微信的 `_adapt_html_for_wechat`） |
| **审核机制** | 头条和抖音都有内容审核，发布后状态是 PENDING，需轮询 |
| **API 权限** | 需要企业资质申请，测试号功能受限 |
| **发布限制** | 每日发布次数有上限，需在 UI 上提示 |
| **remote_id 格式** | 提前规划好存储格式（参考微信用逗号分隔多值） |

---

## 九、验收标准

- [ ] 用户可在配置页面添加头条号/抖音账号（填入 client_key + client_secret）
- [ ] 用户可在发布对话框中选择"头条号"或"抖音" Tab
- [ ] 点击发布后，文章成功提交到对应平台
- [ ] 发布记录中可查看状态（PENDING/SUCCESS/FAILED）
- [ ] token 过期时自动刷新，不需用户手动操作
- [ ] 发布失败时显示明确的错误信息
- [ ] 前端 TypeScript 编译通过，后端 ruff lint 通过

---

## 十、环境搭建（必须先完成）

### 10.1 获取源码

```bash
# 方式一：从 Gitee 克隆
git clone https://gitee.com/fengneng_2/geo.git
cd geo
git checkout feat/phase3-celery-and-search

# 方式二：从同事处获取压缩包（公司网络可能连不上 Gitee）
# 解压 fnai-monorepo.zip 到本地
```

### 10.2 前置依赖

| 工具 | 版本要求 | 用途 |
|------|---------|------|
| Docker Desktop | 最新版（WSL2 后端） | 运行所有服务 |
| Node.js | 22+ | 前端构建（可选，Docker 内会装） |
| Python | 3.12+ | 后端（可选，Docker 内会装） |
| Git | 任意 | 版本管理 |

### 10.3 一键启动本地环境

```bash
# 1. 进入 infra 目录
cd fnai-monorepo/infra

# 2. 启动开发栈（backend + frontend + celery-worker，复用外部 postgres + redis）
docker compose -f docker-compose.dev.yml up -d --build

# 3. 创建数据库表（首次启动需要）
docker exec fnai-backend-dev python -m app.db.init_db

# 4. 验证服务正常
curl http://localhost:8000/api/v1/health    # → {"status":"ok"}
curl http://localhost:3000/                  # → HTML 页面
```

### 10.4 端口说明

| 端口 | 服务 | 访问地址 |
|------|------|---------|
| 3000 | 前端（nginx） | http://localhost:3000 |
| 8000 | 后端（FastAPI） | http://localhost:8000/docs （API 文档） |
| 5432 | PostgreSQL + pgvector | 外部容器共享 |
| 6379 | Redis | 外部容器共享 |

### 10.5 常用调试命令

```bash
# 查看后端实时日志
docker logs -f fnai-backend-dev

# 进入后端容器执行 Python
docker exec -it fnai-backend-dev python

# 查看数据库
docker exec fnai-postgres psql -U fnai -d fnai_dev
# SQL: \dt 列出表 / \d <table> 看表结构 / SELECT * FROM <table> LIMIT 5;

# 前端类型检查
cd fnai-monorepo/frontend && npx tsc --noEmit

# 后端 lint
cd fnai-monorepo/backend && ruff check .
```

---

## 十一、开发上手步骤

1. 读 `docs/HANDOFF.md` 了解项目全局
2. 读本文档了解需求
3. 重点读以下参考文件，理解发布模块的代码模式：
   - `backend/app/services/wechat_mp.py` — 微信 API 客户端（OAuth + 重试 + 错误处理）
   - `backend/app/api/v1/endpoints/wechat_mp.py` — 微信端点（路由 + 权限 + 错误翻译）
   - `backend/app/schemas/wechat.py` — 微信 Schema（请求/响应定义）
   - `frontend/src/components/PublishDialog.tsx` — 前端发布对话框（Tab 切换 + 表单）
   - `frontend/src/pages/WechatConfigPage.tsx` — 微信配置管理页
4. 在浏览器打开 http://localhost:3000 注册账号，体验一遍完整的"创建知识库 → 生成文章 → 发布"流程
5. 在 [头条号开放平台](https://developer.toutiao.com) 和 [抖音开放平台](https://open.douyin.com) 注册开发者应用，获取 `client_key` + `client_secret`
6. 阅读平台 API 文档，重点关注：OAuth 2.0 授权流程、内容发布接口、素材上传接口、状态查询接口
7. 按照本文档第三节"文件清单"逐个实现（先后端 Model → Schema → Service → Endpoint，再前端 API → 发布对话框 → 配置管理页）
8. 每完成一个平台的功能，跑一次完整 E2E 测试验证

---

## 十二、参考资料

- [头条号开放平台](https://developer.toutiao.com)
- [抖音开放平台](https://open.douyin.com)
- [字节跳动统一 OAuth 文档](https://open.douyin.com/platform/resource?doc_id=)
- 项目现有发布模块代码（`services/`、`api/v1/endpoints/`）
- 项目交接文档：`docs/HANDOFF.md`
