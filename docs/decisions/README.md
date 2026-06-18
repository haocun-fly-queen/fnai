# ADR 索引

> 重要决策的目录。修改顺序按编号升序，不要改历史文件的内容。

| 编号 | 标题 | 状态 | 日期 |
|------|------|------|------|
| [0000](./0000-template.md) | 模板 | - | - |
| [0001](./0001-v1-scope.md) | V1 范围重排：14 阶段砍到 7 阶段、42 表砍到 22 表 | Accepted | 2026-06-18 |
| [0002](./0002-tech-stack.md) | 后端选型：FastAPI + SQLAlchemy 2.0 async + PostgreSQL 15 + pgvector | Accepted | 2026-06-18 |
| [0003](./0003-monorepo.md) | 单一仓库多应用管理（monorepo） | Accepted | 2026-06-18 |
| 0004 | 前后端 TypeScript 共享类型 | Proposed | - |

## 写作规范

1. 编号递增，不可重用
2. 文件名：`NNNN-kebab-case-title.md`
3. 状态变更时编辑文件，不要删除
4. 超过 6 个月未引用的 ADR 标记为 Superseded 或 Deprecated
5. 重大决策必须有 ADR，否则代码审查不通过
