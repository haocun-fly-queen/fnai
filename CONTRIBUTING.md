# 贡献指南

> 贡献前请阅读 [阶段 1 Runbook](./docs/phase-1-runbook.md)、[代码审查 Checklist](./docs/code-review-checklist.md) 和 [提交规范](./docs/commit-convention.md)。

## 快速链接

- 📖 [V1 范围砍掉清单](../v1-scope-cut-list.md)
- 📋 [V1 开发阶段](../v1-development-phases.md)
- 📊 [团队技术能力提升计划](../team-tech-improvement-plan.md)
- 🏛️ [架构决策记录 (ADR)](./decisions/README.md)

## 开发流程

1. 从 `develop` 拉分支：`git checkout -b feat/xxx`
2. 开发 + 自测 + Pre-commit 检查
3. 推送到远端：`git push -u origin feat/xxx`
4. 开 PR，关联 issue/任务
5. CI 通过 + 至少 1 名审查者 LGTM
6. Squash merge 到 `develop`

## 提交规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/)。Pre-commit 钩子会校验。

```
feat(auth): add JWT refresh token rotation
fix(article): resolve race condition in version save
docs(readme): update setup instructions
```

## 紧急修复

`main` 分支保护，但生产紧急修复：
1. 从 `main` 拉 `hotfix/xxx` 分支
2. 修复 + 加测试
3. 紧急 PR 合并到 `main` + `develop`
4. 立即部署

## 行为准则

- 友善、专业、建设性
- 接受批评，承认错误
- 关注对团队最有利的事
- 假设对方出于善意
