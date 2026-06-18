# ADR 0003: Monorepo 仓库结构

- **状态：** Accepted
- **日期：** 2026-06-18
- **决策人：** 苏苏、Senior Developer、后端主程、前端负责人
- **影响范围：** 全部 7 人研发团队、CI/CD、文档

## 背景与问题

FNAI 平台涉及多个应用：
- `backend` - FastAPI 主后端
- `frontend` - 主用户前端
- `admin` - 管理后台（V1 暂不实现，V1.5 启动）
- `packages/shared` - 前后端共享类型

需要决定：单一仓库（monorepo）还是多仓库（polyrepo）？

## 考虑的选项

### 选项 A：Polyrepo（每个应用一个仓库）

- 优点：权限隔离清晰；CI 可独立配置
- 缺点：跨应用改 PR 难；共享代码靠 npm 私有包；版本管理复杂

### 选项 B：Monorepo（单一仓库多应用）

- 优点：原子化跨应用变更；共享代码简单；统一规范
- 缺点：仓库体积增长；CI 需要按路径触发；权限管理弱

### 选项 C：Git submodule 拼装

- 优点：兼顾 monorepo 便利和独立仓库
- 缺点：submodule 学习成本；新人容易踩坑

## 决策

**采用选项 B：Monorepo 单一仓库管理。**

应用通过目录区分：`backend/`、`frontend/`、`admin/`、`packages/shared/`、`infra/`。

## 理由

1. **共享类型**：前后端共享 `packages/shared/ts/`，避免 API 契约漂移
2. **跨应用 PR**：例如前后端 API 变更可以一次 PR 完成
3. **CI 配置集中**：一套 lint/format/test 规则
4. **7 人团队**规模适中，权限管理复杂度低
5. **未来拆分容易**：monorepo 可以平滑拆分为 polyrepo

## 后果

### 正面

- 代码同步：所有人在同一仓库看完整代码
- 重构便利：跨应用重构不踩版本坑
- 文档集中：ADR、Runbook、API 契约在 `docs/` 统一管理

### 负面

- 仓库体积可能增长到 1GB+（含 node_modules、迁移文件）— 缓解：`.gitignore` 严格
- CI 需要按路径触发，否则全量跑慢 — 缓解：`paths:` 过滤
- Git 操作略慢 — 缓解：可考虑 sparse-checkout

### 风险与缓解

- **风险：CI 全量跑慢**
  - **缓解：** 在 `.github/workflows/ci.yml` 中按 `paths` 过滤
- **风险：未来 monorepo 拆分困难**
  - **缓解：** 用相对路径保持模块边界清晰

## 目录结构

```
fnai-monorepo/
├── backend/                # FastAPI
├── frontend/               # 主应用
├── admin/                  # 管理后台（V1.5 启动）
├── packages/shared/        # 共享代码
├── infra/                  # Docker Compose / 监控
├── docs/                   # ADR、Runbook、规范
└── .github/workflows/      # CI
```

## 相关资料

- [Monorepo 工具对比](https://monorepo.tools/)
- [Turborepo](https://turbo.build/) - V1.5 阶段可考虑引入
