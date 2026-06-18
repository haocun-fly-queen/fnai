# Frontend (FNAI / Vite + React)

## 开发

```bash
npm install
cp .env.example .env
npm run dev
```

打开 http://localhost:5173

后端 API 自动代理到 `http://localhost:8000`。

## 脚本

| 命令 | 用途 |
|------|------|
| `npm run dev` | 启动开发服务器 |
| `npm run build` | 生产构建 |
| `npm run preview` | 预览构建产物 |
| `npm run lint` | ESLint 检查 |
| `npm run lint:fix` | 自动修复 |
| `npm run format` | Prettier 格式化 |
| `npm run type-check` | TypeScript 类型检查（不构建） |
| `npm run test` | 跑测试 |
| `npm run test:coverage` | 测试 + 覆盖率 |

## 项目结构

```
src/
├── components/    # 通用组件
├── pages/         # 页面（按路由拆分）
├── hooks/         # 自定义 hooks
├── lib/           # 工具、Axios 实例
├── stores/        # Zustand 状态
└── types/         # TypeScript 类型
```

## 规范

- **类型**：禁止 `any`，所有 props 必须有 interface
- **样式**：禁止硬编码颜色，全部走 Tailwind + design token
- **状态**：服务端状态用 React Query，客户端全局状态用 Zustand
- **表单**：用 React Hook Form + Zod
- **API**：用统一的 `api` 实例（`src/lib/api.ts`），不要直接 axios

## 性能

- 列表渲染：用 `react-window`（V1 阶段 4 接入）
- 图片：使用 WebP，关键图加 `loading="lazy"`
- 代码分割：用 `React.lazy` 做路由级分割
- 避免不必要 re-render：合理使用 `memo` / `useMemo` / `useCallback`
