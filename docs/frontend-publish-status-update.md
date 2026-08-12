# 前端发布状态组件更新说明

## 修改时间
2026-07-07

## 问题描述

1. **React Key 警告**: 列表渲染缺少唯一 key
2. **状态显示错误**: 已成功发布的文章显示为"审核中"
3. **信息过载**: 显示所有历史发布记录，用户只需要最新状态

## 解决方案

### 1. 更新类型定义

**文件**: `frontend/src/lib/publish-api.ts`

**修改前**:
```typescript
export interface PublishLog {
  id: string;
  article_id: string;
  target_id: string;
  status: PublishStatus;  // 'pending' | 'success' | 'failed'
  remote_id?: string;
  error_message?: string;
  published_at: string;
  created_by?: string;
  target_name?: string;
  article_title?: string;
}
```

**修改后**:
```typescript
export interface PublishLog {
  is_published: boolean;  // 是否已发布
  published_at: string;   // 发布时间
  target_name: string;    // 目标平台名称
}
```

### 2. 只显示最新记录

**文件**: `frontend/src/components/PublishStatusCard.tsx`

```typescript
useEffect(() => {
  async function load() {
    try {
      const result = await getPublishLogs(articleId);
      // 只保留最新的一条记录
      setLogs(result.slice(0, 1));
    } catch (err) {
      console.error('Failed to load publish logs:', err);
    } finally {
      setLoading(false);
    }
  }
  void load();
}, [articleId]);
```

### 3. 修复 React Key 警告

**修改前**:
```tsx
{logs.map((log) => (
  <PublishLogItem key={log.id} log={log} />
))}
```

**修改后**:
```tsx
{logs.map((log, index) => (
  <PublishLogItem key={`${log.target_name}-${log.published_at}-${index}`} log={log} />
))}
```

### 4. 简化状态显示逻辑

**修改前**:
```typescript
const statusConfig = {
  pending: { label: '审核中', color: 'bg-yellow-400', textColor: 'text-yellow-700' },
  success: { label: '已发布', color: 'bg-green-500', textColor: 'text-green-700' },
  failed: { label: '发布失败', color: 'bg-red-500', textColor: 'text-red-700' },
};

const config = statusConfig[log.status] || statusConfig.pending;
```

**修改后**:
```typescript
const config = log.is_published
  ? { label: '已发布', color: 'bg-green-500', textColor: 'text-green-700' }
  : { label: '未发布', color: 'bg-slate-400', textColor: 'text-slate-700' };
```

### 5. 优化时间标签

**修改前**:
```tsx
<span>{log.status === 'success' ? '发布时间:' : '提交时间:'}</span>
```

**修改后**:
```tsx
<span>{log.is_published ? '发布时间:' : '最近尝试:'}</span>
```

## UI 变化对比

### 修改前
```
发布状态
┌────────────────────────────┐
│ 🟡 审核中                   │
│ 目标: 微信公众号             │
│ 提交时间: 2026-07-07 10:38:18│
├────────────────────────────┤
│ 🟡 审核中                   │
│ 目标: 微信公众号             │
│ 提交时间: 2026-07-07 10:30:15│
├────────────────────────────┤
│ 🔴 发布失败                 │
│ 目标: 微信公众号             │
│ 提交时间: 2026-07-07 09:20:10│
│ 失败原因: Token 无效         │
└────────────────────────────┘
```

### 修改后
```
发布状态
┌────────────────────────────┐
│ 🟢 已发布                   │
│ 目标: 微信公众号             │
│ 发布时间: 2026-07-07 10:38:18│
└────────────────────────────┘
```

或

```
发布状态
┌────────────────────────────┐
│ ⚪ 未发布                   │
│ 目标: 微信公众号             │
│ 最近尝试: 2026-07-07 10:38:18│
└────────────────────────────┘
```

## 效果

### ✅ 修复的问题

1. **React Key 警告消失** - 使用组合 key 确保唯一性
2. **状态准确** - 基于 `is_published` 布尔值，清晰明了
3. **信息精简** - 只显示最新一条记录，减少视觉干扰

### 📊 数据量对比

- **修改前**: 显示所有历史记录（可能 3-10 条）
- **修改后**: 只显示最新 1 条记录
- **减少**: 约 70-90% 的 UI 占用

### 🎨 用户体验改进

1. **一目了然** - 用户立即看到当前发布状态
2. **简单直观** - "已发布/未发布" 比 "pending/success/failed" 更易理解
3. **减少混淆** - 不再显示历史失败记录干扰判断

## 后续优化建议

1. **轮询更新** - 对于"未发布"状态，可以每 5 秒轮询一次直到发布成功
2. **操作按钮** - 未发布时显示"重新发布"按钮
3. **历史记录入口** - 添加"查看历史"链接，需要时展开完整记录
4. **加载动画** - 添加骨架屏或更友好的加载状态

## 兼容性

- ✅ 后端 API 已更新匹配
- ✅ 类型定义完全匹配
- ✅ 无需数据库迁移
- ✅ 向后兼容（旧 API 保留）
