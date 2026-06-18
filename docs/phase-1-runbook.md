# 阶段 1 Runbook（W1-W2 工程化基础）

> 本周目标：**7 人都能在本地跑起来 + 1 个示例 PR 通过 CI + 代码审查。**
> 适用范围：2026-06-18 → 2026-07-01（共 2 周）

## 📋 阶段 1 任务总览

| # | 任务 | 负责人 | 完成标准 |
|---|------|--------|----------|
| 1.1 | 创建代码仓库（GitHub 或 Gitee） | 苏苏 / 后端 A | 仓库可访问，团队 7 人都加入 |
| 1.2 | 推 monorepo 骨架代码 | 后端 A | 仓库含 backend/frontend/infra/docs |
| 1.3 | 本地环境搭建 1v1 帮带 | 后端 A / 前端 A | 7 人全部 `curl /api/v1/health` 返回 ok |
| 1.4 | 安装 Pre-commit | 全员 | `git commit` 会自动跑格式检查 |
| 1.5 | 配置 CI | 后端 A | PR 触发后 CI 能在 5 分钟内跑完 |
| 1.6 | 写第一份 ADR-0001 | 苏苏 | V1 范围决策已记录 |
| 1.7 | 规范宣讲会 | 苏苏 | 团队 7 人 + Senior Developer 一起过一遍规范 |
| 1.8 | 第一个示例 PR | 全员 | 改一行 README，通过 PR + CI + 审查 |
| 1.9 | 文档同步 | 后端 A | README + 各应用 README 完整 |
| 1.10 | 监控接入 | 后端 A | Sentry + Prometheus 接入，dev 环境能上报 |

---

## 🗓 每日时间线（建议）

### Day 1（今天）

**上午：仓库与代码**
- 苏苏：创建仓库 + 拉团队成员进来
- 后端 A：把 monorepo 骨架推上去
- 全员：clone 仓库，`git remote -v` 确认

**下午：本地环境**
- 后端 A + 前端 A：1v1 帮装 Python、Node、Docker
- 全员：跑 `docker compose -f infra/docker-compose.yml up -d`
- 验证：`curl http://localhost:8000/api/v1/health`

### Day 2

**上午：Pre-commit 安装**
- 全员：`pip install pre-commit && pre-commit install`
- 验证：改一行代码 `git commit`，看到自动跑 ruff/prettier

**下午：CI 配通**
- 后端 A：配 GitHub Actions（或 Gitee CI）
- 提交 1 个测试 PR，确认 CI 跑通

### Day 3

**上午：规范宣讲会（30 分钟）**
- 苏苏主持
- 重点：提交规范 + 代码审查 Checklist
- 全员认领本周质量官

**下午：第一个示例 PR**
- 全员：发个 `docs:` 提交，更新 README 中自己的名字
- 走完整 PR → CI → 审查 → 合并 流程

### Day 4-5

**缓冲时间：**
- 解决 Day 1-3 出现的问题
- 完善 CI（加缓存、加并行）
- 写 ADR-0001 / 0002 / 0003（已完成）

### Day 6-7（周末）

- 全员休整
- 苏苏：review 本周进度，写阶段 1 总结

### Day 8-10（W2）

**方向：补漏 + 进入阶段 2 准备**
- 修阶段 1 暴露的问题
- 全员读 `v1-development-phases.md` 中阶段 2 内容
- 阶段 2 kick-off：认证与多租户任务分解
- 准备阶段 2 所需的数据库表设计（tenant / user / tenant_member）

---

## 🚨 常见坑（提前预警）

| 坑 | 症状 | 解决 |
|------|------|------|
| **Docker 端口冲突** | `port 5432 already in use` | `netstat -ano \| findstr :5432` 找占用，杀进程或改端口 |
| **WSL2 性能差** | 文件 I/O 慢，监控无响应 | 把代码 clone 到 WSL 内部，不要放 Windows 文件系统 |
| **pgvector 镜像拉取慢** | docker pull 卡顿 | 配国内镜像；或换 `ankane/pgvector:latest` |
| **Pre-commit 卡在第一次** | 第一次跑会下 hook 镜像，慢 | 等几分钟，后续会快很多 |
| **CI 缓存不命中** | 每次都重装依赖 | 检查 `cache-dependency-path` 路径是否正确 |
| **Windows 长路径问题** | npm install 报错 | 管理员运行 `git config --system core.longpaths true` |
| **Python 3.12 未装** | 报 "no python interpreter" | 装 pyenv 或从 python.org 下 3.12 |
| **前端首次启动慢** | vite 第一次 build 慢 | 正常现象，第二次会快很多 |

---

## 📞 求助通道

- **阻塞问题**（超过 30 分钟没解决）：在团队群 @ Senior Developer
- **环境问题**：找后端 A 或前端 A
- **规范问题**：找本周质量官
- **决策问题**：找苏苏

---

## ✅ 阶段 1 DoD 验收清单

进入阶段 2 前，必须**全部勾选**：

- [ ] 7 人本地环境都跑通了
- [ ] 至少 2 个 PR 通过 CI + 审查并合并
- [ ] Pre-commit 实际跑起来 1 次以上
- [ ] Sentry dev 环境能收到测试事件
- [ ] 团队 7 人都听过规范宣讲
- [ ] ADR-0001 / 0002 / 0003 都已写完
- [ ] 阶段 1 总结会开完（10 分钟）
- [ ] 本周质量官提交了 1 份审查审计

---

## 🎯 阶段 1 验收后下一步

如果 DoD 全绿，立即：
1. 召开 30 分钟阶段 2 kick-off
2. 拆分阶段 2 任务（认证与多租户）
3. 后端 A 开始写 `tenant`、`user`、`tenant_member` 三张表的 SQLAlchemy 模型
4. 后端 B 写认证 API（注册/登录/刷新/登出）
5. 前端 A 写登录/注册页

---

*阶段 1 是最无聊的 2 周，也是最重要的 2 周。打地基比盖楼难。*
