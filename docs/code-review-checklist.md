# FNAI 代码审查 Checklist

> 每个 PR 必须由审查者逐项勾选。质量官每周轮值负责审计执行率。
> 适用：所有 backend / frontend / infra 变更。

---

## 🔒 必查项（P0 - 阻塞合并）

### 安全

- [ ] **多租户隔离**：所有 SQL 查询都包含 `tenant_id` 过滤（核心安全线）
- [ ] **无硬编码密钥**：没有把 `OPENAI_API_KEY` / `JWT_SECRET` 写死在代码里
- [ ] **敏感数据加密**：密码用 bcrypt 哈希，API Key 用 Fernet/AES 加密存储
- [ ] **输入校验**：所有外部输入（用户输入、URL 参数、文件）都经过 Pydantic/Zod 校验
- [ ] **无 SQL 注入**：使用 ORM 或参数化查询，无字符串拼接
- [ ] **无 XSS**：前端用 React 默认转义，禁止 `dangerouslySetInnerHTML`（除明确豁免）

### 数据完整性

- [ ] **迁移存在**：新增/修改的模型有对应的 Alembic 迁移
- [ ] **软删除规范**：使用 `deleted_at` 字段，不用 `DELETE`
- [ ] **时间字段**：使用 `TIMESTAMPTZ`，不用 `TIMESTAMP`
- [ ] **外键约束**：关联表之间有 `FOREIGN KEY`
- [ ] **索引合理**：WHERE 条件字段、JOIN 字段有索引

### 测试覆盖

- [ ] **新增逻辑有测试**：单元测试 / 集成测试覆盖新增业务逻辑
- [ ] **关键路径有 E2E**：登录、核心 CRUD、AI 生成链路有 E2E 或集成测试
- [ ] **覆盖率达标**：后端 service 层覆盖率 ≥ 60%（V1），前端工具/hooks ≥ 50%

---

## ✅ 必查项（P1 - 应在合并前完成）

### 代码质量

- [ ] **无 `any` 类型**（前端 TypeScript）
- [ ] **无 `print` 调试代码**（用 `logger`）
- [ ] **无 console.log**（前端，用 console.warn/error 或去掉）
- [ ] **无 TODO/FIXME 未处理**（如保留，必须有 issue 链接）
- [ ] **无注释掉的代码块**（删掉，git 会记住）
- [ ] **函数长度**：单个函数不超过 50 行（不含 docstring）
- [ ] **文件长度**：单个文件不超过 500 行

### 性能

- [ ] **避免 N+1 查询**：列表接口用 `selectinload` / `joinedload` 预加载
- [ ] **分页**：列表接口有 `limit` / `offset` 或游标分页
- [ ] **缓存合理**：高频读、慢查询走 Redis（标记 TTL）
- [ ] **大文件不阻塞**：上传/解析走异步任务（Celery）

### 错误处理

- [ ] **异常不静默**：try/except 必须有日志或重新抛出
- [ ] **用户友好错误**：4xx 错误有明确 message，5xx 错误不暴露内部细节
- [ ] **API 错误格式统一**：使用 `ApiError`，格式 `{code, message, details}`

### 文档

- [ ] **PR 描述完整**：包含变更说明、测试证据、影响范围、相关 issue
- [ ] **复杂逻辑有注释**：why 注释（不是 what 注释）
- [ ] **API 变更更新文档**：改了 OpenAPI 字段就更新契约

---

## 📋 加分项（P2 - 鼓励但非阻塞）

- [ ] **设计/架构**：使用现有模式，避免引入新依赖
- [ ] **可观测性**：关键路径有埋点（Sentry / Prometheus counter）
- [ ] **可回滚**：数据库迁移有 `downgrade()`，功能开关支持快速回滚
- [ ] **国际化**：文案集中管理，不硬编码中文/英文字符串
- [ ] **无障碍 (a11y)**：交互元素有 `aria-*`，键盘可达
- [ ] **响应式**：移动端布局可用

---

## 🎯 领域专项 Checklist

### 后端 API 新增

- [ ] 路由都是 `async def`
- [ ] 使用 `get_db` 依赖注入
- [ ] 使用 Pydantic schema 做请求/响应模型
- [ ] 业务逻辑放在 `services/`，路由只做编排
- [ ] 权限检查在依赖项中完成（`get_current_user`）
- [ ] OpenAPI 文档描述完整（summary、description、tags）

### 前端组件新增

- [ ] props 有明确的 TypeScript interface
- [ ] 默认值用 ES default，不是 `||`
- [ ] 错误状态有 UI 反馈（toast、inline error）
- [ ] loading 状态有 UI 反馈（skeleton、spinner）
- [ ] 空状态有 UI 反馈（empty illustration）
- [ ] 复杂组件有 storybook 或示例

### AI 相关变更

- [ ] Prompt 模板版本化（写库 + Git）
- [ ] 新增 prompt 有 5+ 测试用例
- [ ] 重要 prompt 变更前在测试集上跑 A/B
- [ ] 失败有 fallback（备用模型 / 简单模板）
- [ ] 记录到 `model_call_log`

### 数据库变更

- [ ] 新表包含 `tenant_id`、`created_at`、`updated_at`
- [ ] 枚举用 CHECK 约束或 PG ENUM
- [ ] 大表考虑分区（按月/按租户）
- [ ] 索引覆盖所有 WHERE 条件
- [ ] 软删除索引化（`WHERE deleted_at IS NULL`）

### 部署 / 配置变更

- [ ] 改 env vars 同时改 `.env.example`
- [ ] 改 docker compose 同步更新 README
- [ ] 破坏性变更标注 ⚠️ BREAKING
- [ ] 数据库迁移生产前先在 staging 验证
- [ ] 配套回滚步骤

---

## 📝 审查者备注模板

```markdown
### ✅ 优点
- ...

### ⚠️ 必须修改（合并前）
- [ ] ...

### 💡 建议（合并后可优化）
- [ ] ...

### 📊 测试结果
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] 手动验证

### 🟢 审查结论
- [ ] LGTM（可合并）
- [ ] 需要修改
- [ ] 拒绝
```

---

## 🚨 红旗（直接拒绝）

- ❌ 绕过认证 / 权限检查
- ❌ 跨租户访问（无 tenant_id 过滤）
- ❌ 直接 `rm -rf` / `DELETE FROM` 无备份
- ❌ 把 `.env` / 密钥提交到仓库
- ❌ 注释掉的代码 / 调试代码
- ❌ 无测试的"修复"
- ❌ 一次 PR 改动超过 800 行（应拆分）

---

## 📈 审查者轮值

| 周次 | 质量官 |
|------|--------|
| W1 | (指定) |
| W2 | (指定) |
| ... | (轮值表见团队文档) |

质量官职责：
1. 抽查本周期内 30% 的 PR
2. 审计 Checklist 执行率
3. 周会汇报技术债与改进点
