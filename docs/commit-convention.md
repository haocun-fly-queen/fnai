# FNAI 提交规范

采用 [Conventional Commits 1.0.0](https://www.conventionalcommits.org/)。Pre-commit 钩子会自动校验。

## 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Type

| Type | 说明 | 示例 |
|------|------|------|
| `feat` | 新功能 | `feat(auth): add JWT refresh token rotation` |
| `fix` | Bug 修复 | `fix(article): resolve race condition in version save` |
| `refactor` | 重构（既不是新功能也不是 bug 修复） | `refactor(db): extract tenant filter into mixin` |
| `perf` | 性能优化 | `perf(rag): cache embedding responses` |
| `test` | 测试相关 | `test(auth): add tenant isolation test` |
| `docs` | 文档 | `docs(readme): update setup instructions` |
| `style` | 代码格式（不影响逻辑） | `style(backend): run ruff format` |
| `chore` | 杂项（构建、依赖、CI） | `chore(deps): bump fastapi to 0.115` |
| `ci` | CI 配置 | `ci(github): add frontend typecheck job` |
| `revert` | 回滚 | `revert: feat(auth): add JWT refresh` |

## Scope

按业务领域划分，必须从以下选项中选：

- `auth` - 认证 / 授权
- `tenant` - 多租户
- `kb` - 知识库
- `rag` - RAG 检索
- `article` - 文章生成
- `prompt` - Prompt 模板
- `publish` - 发布
- `model` - AI 模型
- `frontend` - 前端通用
- `backend` - 后端通用
- `infra` - 基础设施 / Docker
- `ci` - CI/CD
- `docs` - 文档
- `deps` - 依赖
- (无 scope) - 跨领域或杂项

## Subject

- 用祈使句，现在时：`add` 而不是 `added` 或 `adds`
- 不大写首字母
- 不加句号
- 不超过 50 字符
- 简洁说明「做了什么」

## Body（可选）

- 解释「为什么」而不是「做什么」
- 与 subject 之间空一行
- 每行不超过 72 字符

## Footer（可选）

- 引用 issue：`Refs #123` / `Closes #456`
- 标记 BREAKING CHANGE：

```
feat(api)!: change article status enum

BREAKING CHANGE: article.status field changed from string to enum
Migration script: alembic upgrade head
```

- `!` 放在 type 后或 footer 中

## 示例

### 简单 feat

```
feat(auth): add email verification endpoint
```

### 带 body

```
fix(rag): handle empty query gracefully

Previously, posting an empty query to /api/v1/kb/{id}/search
would raise a 500. Now returns 400 with a clear message.
```

### 带 BREAKING CHANGE

```
feat(api)!: change authentication response format

BREAKING CHANGE: /auth/login now returns {user, tokens} instead of
just tokens. Update frontend to use response.user.
```

## PR 标题

PR 标题**必须**遵循与 commit 相同的格式（如果 squash merge 则与最终 commit 一致）。

## CHANGELOG

- 工具：standard-version 或 release-please
- 自动从 conventional commits 生成 CHANGELOG.md
- 每周五由 release-please 自动开 release PR

## 工具

```bash
# 推荐 commitizen 交互式提交
npm install -g commitizen cz-conventional-changelog
echo '{ "path": "cz-conventional-changelog" }' > ~/.czrc
git cz
```

或者直接 `git commit -m "feat(auth): xxx"`。
