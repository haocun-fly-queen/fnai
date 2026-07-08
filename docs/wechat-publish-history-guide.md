# 微信发布历史功能使用指南

## ✅ 已完成

已为测试号（wx9fd8b428a5485411）添加发布历史功能。

---

## 📡 后端API

### 获取文章的微信发布历史

**接口：**
```
GET /api/v1/wechat/articles/{article_id}/publish-history
```

**响应示例：**
```json
{
  "total": 2,
  "items": [
    {
      "id": "4336a0c7-0c36-4a09-9d34-5861e1e5039b",
      "publish_id": "2247483661",
      "status": "success",
      "published_at": "2026-07-07T09:49:53.206677",
      "error_message": null,
      "article_url": "http://mp.weixin.qq.com/s?__biz=MzY5NTM3NzYzNg==&mid=2247483661&idx=1&sn=..."
    },
    {
      "id": "02d3483f-721f-41db-a128-7f498221fbc3",
      "publish_id": null,
      "status": "failed",
      "published_at": "2026-07-07T09:44:58.081475",
      "error_message": "创建草稿失败: invalid credential",
      "article_url": null
    }
  ]
}
```

**字段说明：**
- `status`: 发布状态
  - `success` - ✅ 发布成功
  - `pending` - ⏳ 处理中
  - `failed` - ❌ 发布失败
- `article_url`: 文章链接（仅成功时有值）
- `error_message`: 错误信息（仅失败时有值）

---

## 🎨 前端组件

### React组件

已创建：`frontend/src/components/WechatPublishHistory.tsx`

**使用方法：**

```tsx
import { WechatPublishHistory } from '@/components/WechatPublishHistory';

function ArticleDetailPage() {
  const articleId = "bb72cf0b-7949-47c7-a41b-9d684f3cade2";
  
  return (
    <div>
      <h1>文章详情</h1>
      
      {/* 其他内容 */}
      
      {/* 添加发布历史组件 */}
      <WechatPublishHistory articleId={articleId} />
    </div>
  );
}
```

### 组件功能

1. **自动加载** - 页面打开时自动获取发布历史
2. **刷新按钮** - 点击刷新最新状态
3. **状态展示** - 清晰显示成功/失败/处理中
4. **复制链接** - 一键复制文章链接
5. **预览文章** - 在新窗口打开文章
6. **查看错误** - 失败时显示具体错误信息

### 界面预览

```
┌───────────────────────────────────────────────────────┐
│ 微信发布历史                              [🔄 刷新]    │
├───────────────────────────────────────────────────────┤
│ 发布时间           状态         操作                   │
├───────────────────────────────────────────────────────┤
│ 2026-07-07 17:49   ✅ 成功     [📋 复制链接] [🔗 预览] │
│ 2026-07-07 17:44   ❌ 失败     [查看错误]             │
│ 2026-07-07 15:30   ⏳ 处理中   等待完成...            │
└───────────────────────────────────────────────────────┘
```

---

## 📋 集成步骤

### 1. 导入组件

在文章详情页导入组件：

```tsx
import { WechatPublishHistory } from '@/components/WechatPublishHistory';
```

### 2. 使用组件

在文章详情页面添加组件，传入文章ID：

```tsx
<WechatPublishHistory articleId={article.id} />
```

### 3. 调整样式（可选）

如果需要自定义样式，可以修改组件内的 `<style jsx>` 部分。

---

## 🎯 用户操作流程

### 发布文章后查看历史

1. **发布文章**
   - 点击"发布到微信"按钮
   - 等待几秒钟

2. **查看发布历史**
   - 页面自动显示最新的发布记录
   - 或点击"刷新"按钮更新

3. **发布成功**
   - 看到 ✅ 成功 标记
   - 点击"复制链接"
   - 发给需要查看文章的同事

4. **发布失败**
   - 看到 ❌ 失败 标记
   - 点击"查看错误"了解失败原因
   - 修复问题后重新发布

5. **处理中**
   - 看到 ⏳ 处理中 标记
   - 等待几秒后点击"刷新"
   - 直到状态变为成功或失败

---

## 🔧 技术细节

### 自动刷新机制

组件可以添加自动轮询功能，当有"处理中"的记录时：

```tsx
useEffect(() => {
  if (history?.items.some(item => item.status === 'pending')) {
    const timer = setTimeout(() => {
      fetchHistory();
    }, 3000); // 3秒后自动刷新
    
    return () => clearTimeout(timer);
  }
}, [history]);
```

### 权限控制

- 需要 `VIEWER` 及以上角色才能查看发布历史
- 接口会自动验证用户权限和文章归属

### 性能优化

- 只查询测试号（wx9fd8b428a5485411）的发布记录
- 按发布时间倒序排列，最新的在最上面
- article_url 在需要时动态获取

---

## 📱 手机端优化（可选）

如果需要适配手机端，可以添加响应式样式：

```css
@media (max-width: 768px) {
  table {
    font-size: 0.875rem;
  }
  
  .actions {
    flex-direction: column;
  }
  
  .btn {
    width: 100%;
  }
}
```

---

## 🐛 常见问题

### Q1: 发布历史为空？

**A:** 可能原因：
- 文章还没有发布过
- 只查询测试号（wx9fd8b428a5485411）的记录
- 文章ID不正确

### Q2: 看不到文章链接？

**A:** 可能原因：
- 发布状态不是"成功"
- 微信API查询失败（会在控制台看到警告）
- 刷新后应该能看到

### Q3: 如何添加其他公众号的历史？

**A:** 修改后端代码中的硬编码部分：

```python
# 目前只查询测试号
if config.config.get("app_id") == "wx9fd8b428a5485411":
    test_config_id = config.id
    break

# 改为查询所有公众号
# 移除上面的过滤逻辑即可
```

---

## ✨ 下一步改进建议

1. **添加自动轮询** - 当有"处理中"的记录时自动刷新
2. **添加分页** - 如果发布记录很多，添加分页功能
3. **添加筛选** - 按状态筛选（只看成功/失败）
4. **添加导出** - 导出发布历史为Excel
5. **添加通知** - 发布成功/失败时显示浏览器通知

---

## 📞 需要帮助？

如果遇到问题：
1. 检查浏览器控制台的错误信息
2. 检查后端日志：`docker logs fnai-backend-dev`
3. 确认API接口是否正常：`curl http://localhost:8000/api/v1/wechat/articles/{article_id}/publish-history`
