# 微信公众号发布指南

## 如何判断文章发布成功？

### 方法1：查看前端发布状态（推荐）

**发布流程：**

1. **点击"发布到微信"按钮**
   - 系统提交发布任务
   - 返回发布ID（publish_id）

2. **等待发布完成（自动轮询）**
   - 前端每2-3秒自动查询发布状态
   - 状态说明：
     - `publish_status = 0` → ✅ 发布成功
     - `publish_status = 1` → ⏳ 发布中（继续等待）
     - `publish_status >= 2` → ❌ 发布失败

3. **发布成功后显示**
   ```
   ✅ 发布成功！
   
   文章链接：http://mp.weixin.qq.com/s?__biz=...
   
   [复制链接] [在微信中打开]
   
   💡 提示：测试号文章不会自动推送给粉丝，
         请将链接分享给需要查看的人
   ```

### 方法2：手动查询API

**查询发布状态：**
```bash
GET /api/v1/wechat/publish-wechat/status/{publish_id}
```

**响应示例（发布成功）：**
```json
{
  "publish_id": "2247483661",
  "publish_status": 0,
  "article_id": "MYDtrZVgZpZyejLFTkw9M...",
  "article_url": "http://mp.weixin.qq.com/s?__biz=MzY5NTM3NzYzNg==&mid=2247483661&idx=1&sn=...",
  "fail_reason": null
}
```

**字段说明：**
- `publish_status`: 0=成功, 1=发布中, 2+=失败
- `article_url`: 文章链接（成功后有值）
- `fail_reason`: 失败原因（失败时有值）

### 方法3：登录微信公众号后台查看

1. 访问测试号后台：https://mp.weixin.qq.com/debug/cgi-bin/sandbox
2. 登录后进入 **素材管理** → **已发布**
3. 可以看到所有已发布的文章列表
4. 点击文章可以预览和获取链接

---

## 重要提示：测试号的限制

### ❌ 测试号不支持的功能

1. **自动推送给粉丝**
   - 测试号发布文章后，不会自动推送通知给关注的粉丝
   - 粉丝不会在微信中收到新文章提醒

2. **群发消息**
   - 测试号不支持群发接口
   - 只有认证的服务号才支持群发

### ✅ 测试号支持的功能

1. **发布文章到后台**
   - 文章会保存在公众号后台
   - 生成唯一的文章链接

2. **通过链接分享**
   - 可以将文章链接发给任何人
   - 任何人都可以通过链接查看文章

3. **在公众号内查看**
   - 关注测试号的用户可以在公众号内查看历史文章

---

## 常见问题

### Q1: 发布成功了，但关注的粉丝看不到文章？

**A:** 这是正常的！测试号发布文章**不会主动推送**给粉丝。

解决方案：
1. 复制文章链接
2. 发送给需要查看的人
3. 或在微信群/朋友圈分享链接

### Q2: 如何让粉丝能主动找到文章？

**A:** 粉丝可以：
1. 进入公众号
2. 点击底部菜单（如果配置了）
3. 或查看历史消息列表
4. 找到已发布的文章

### Q3: 发布失败怎么办？

**A:** 查看失败原因：
1. 前端会显示具体错误信息
2. 或调用状态查询接口查看 `fail_reason` 字段

常见失败原因：
- `invalid credential`: AppID或AppSecret配置错误
- `access_token过期`: 刷新token即可（系统会自动处理）
- `content too long`: 文章内容超过限制

### Q4: 如何验证文章内容正确？

**A:** 点击文章链接，在微信中打开预览：
1. 复制文章链接
2. 在微信中发给"文件传输助手"
3. 点击链接查看文章内容
4. 确认标题、内容、格式都正确

### Q5: 想要真正的群发功能怎么办？

**A:** 需要申请认证的服务号：
1. 访问微信公众平台：https://mp.weixin.qq.com
2. 注册企业服务号
3. 完成企业认证（需要营业执照等资料）
4. 认证后即可使用群发功能（每月4次）

---

## 前端实现建议

### 发布后自动轮询状态

```typescript
async function publishAndWaitForResult(articleId: string, configId: string) {
  // 1. 提交发布
  const { publish_id } = await publishToWechat(articleId, configId);
  
  // 2. 轮询状态（最多等待30秒）
  let attempts = 0;
  const maxAttempts = 15; // 15次 x 2秒 = 30秒
  
  while (attempts < maxAttempts) {
    await sleep(2000); // 等待2秒
    
    const status = await getPublishStatus(publish_id);
    
    if (status.publish_status === 0) {
      // 发布成功
      return {
        success: true,
        article_url: status.article_url,
        message: '发布成功！'
      };
    } else if (status.publish_status >= 2) {
      // 发布失败
      return {
        success: false,
        message: status.fail_reason || '发布失败'
      };
    }
    
    // 继续等待
    attempts++;
  }
  
  // 超时
  return {
    success: false,
    message: '发布超时，请稍后手动查询状态'
  };
}
```

### 显示成功提示（带链接）

```tsx
{publishResult.success && (
  <div className="success-card">
    <div className="icon">✅</div>
    <h3>发布成功！</h3>
    
    <div className="article-url">
      <label>文章链接：</label>
      <input 
        type="text" 
        readOnly 
        value={publishResult.article_url} 
      />
      <button onClick={() => copyToClipboard(publishResult.article_url)}>
        📋 复制链接
      </button>
      <button onClick={() => window.open(publishResult.article_url)}>
        🔗 打开链接
      </button>
    </div>
    
    <div className="tip">
      💡 测试号文章不会自动推送，请将链接分享给需要查看的人
    </div>
  </div>
)}
```

---

## API端点总结

### 发布文章
```
POST /api/v1/wechat/articles/{article_id}/publish-wechat
```

### 查询发布状态
```
GET /api/v1/wechat/publish-wechat/status/{publish_id}
```

### 管理微信配置
```
GET    /api/v1/wechat/wechat-configs           # 列出配置
POST   /api/v1/wechat/wechat-configs           # 创建配置
PUT    /api/v1/wechat/wechat-configs/{id}      # 更新配置
DELETE /api/v1/wechat/wechat-configs/{id}      # 删除配置
```

---

## 数据库查询（开发调试用）

### 查看最近的发布记录
```sql
SELECT 
  pl.id, 
  a.title, 
  pt.name as target_name,
  pl.status, 
  pl.remote_id, 
  pl.published_at,
  pl.error_message
FROM publish_logs pl
JOIN articles a ON pl.article_id = a.id
JOIN publish_targets pt ON pl.target_id = pt.id
WHERE pt.type = 'WECHAT_MP'
ORDER BY pl.published_at DESC
LIMIT 10;
```

### 查看token缓存状态
```sql
SELECT 
  app_id, 
  LEFT(access_token, 30) as token_prefix, 
  expires_at,
  NOW() as current_time,
  expires_at > NOW() as is_valid
FROM wechat_token_cache;
```
