# 401 错误修复指南

## 问题诊断

当点击"保存"时出现 401 Unauthorized 错误，通常是以下原因之一：

### 1. Token 过期（最常见）
- Access token 默认 15 分钟过期
- 如果 refresh token 也过期了（7天），需要重新登录

### 2. Token 格式错误
- localStorage 中的数据损坏
- Zustand persist 数据结构不正确

### 3. 后端认证配置问题
- JWT_SECRET 不匹配
- 数据库中用户被删除

## 快速修复步骤

### 方法 1：清除缓存并重新登录（最简单）

1. **打开浏览器控制台**（F12）
2. **执行以下命令清除认证状态：**
   ```javascript
   localStorage.removeItem('fnai.auth');
   location.reload();
   ```
3. **重新登录**

### 方法 2：检查 Token 是否过期

1. **打开浏览器控制台**（F12）
2. **执行以下代码检查 Token：**
   ```javascript
   const auth = JSON.parse(localStorage.getItem('fnai.auth'));
   const token = auth.state?.accessToken || auth.accessToken;
   const parts = token.split('.');
   const payload = JSON.parse(atob(parts[1]));
   
   console.log('Token 过期时间:', new Date(payload.exp * 1000));
   console.log('当前时间:', new Date());
   console.log('是否过期:', payload.exp < Date.now() / 1000);
   ```

3. **如果显示"是否过期: true"，执行：**
   ```javascript
   localStorage.removeItem('fnai.auth');
   location.reload();
   ```

### 方法 3：使用调试页面

1. 在浏览器中打开：
   ```
   http://localhost:5173/debug-auth.html
   ```

2. 页面会自动显示：
   - localStorage 内容
   - Token 解析结果
   - Token 是否过期

3. 点击"测试 API 调用"查看详细错误信息

## 预防措施

### 1. 实现自动刷新 Token

前端已经有自动刷新机制（在 `src/lib/api.ts`），但如果 refresh token 也过期了，需要重新登录。

### 2. 添加登录状态检测

在 `src/App.tsx` 或主组件中添加：

```typescript
useEffect(() => {
  const checkAuth = () => {
    const auth = localStorage.getItem('fnai.auth');
    if (!auth) return;
    
    try {
      const parsed = JSON.parse(auth);
      const token = parsed.state?.accessToken || parsed.accessToken;
      if (!token) return;
      
      const parts = token.split('.');
      const payload = JSON.parse(atob(parts[1]));
      
      // 如果 token 即将过期（剩余不到 1 分钟），提示用户
      const timeLeft = payload.exp - Date.now() / 1000;
      if (timeLeft < 60 && timeLeft > 0) {
        console.warn('Token 即将过期，请保存工作');
      }
      
      // 如果 token 已过期，清除并跳转登录
      if (timeLeft < 0) {
        localStorage.removeItem('fnai.auth');
        window.location.href = '/login';
      }
    } catch (e) {
      console.error('Token 检查失败:', e);
    }
  };
  
  // 每分钟检查一次
  const timer = setInterval(checkAuth, 60000);
  checkAuth(); // 立即执行一次
  
  return () => clearInterval(timer);
}, []);
```

### 3. 改善错误提示

在拦截器中添加更友好的提示：

```typescript
// src/lib/api.ts
api.interceptors.response.use(
  (response) => response,
  async (err: AxiosError) => {
    const original = err.config as InternalAxiosRequestConfig & { _retry?: boolean };
    
    if (err.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      const newToken = await tryRefresh();
      
      if (newToken) {
        original.headers.set?.('Authorization', `Bearer ${newToken}`);
        return api.request(original);
      } else {
        // Refresh 失败，提示用户重新登录
        alert('登录已过期，请重新登录');
        localStorage.removeItem('fnai.auth');
        window.location.href = '/login';
      }
    }
    
    return Promise.reject(toApiError(err));
  },
);
```

## 常见问题

### Q: 为什么刚登录就提示 401？
A: 检查后端的 JWT_SECRET 是否和生成 token 时一致。

### Q: 为什么 refresh token 刷新失败？
A: Refresh token 有 7 天有效期，超过后必须重新登录。

### Q: 如何延长 token 有效期？
A: 修改后端 `.env` 文件：
```env
ACCESS_TOKEN_EXPIRE_MINUTES=60  # 改为 60 分钟
REFRESH_TOKEN_EXPIRE_DAYS=30    # 改为 30 天
```

## 验证修复

修复后，按以下步骤验证：

1. **清除缓存并重新登录**
2. **打开一篇文章**
3. **修改标题并保存**
4. **打开浏览器控制台**（F12）→ Network 标签
5. **查看 PATCH 请求：**
   - 状态码应该是 **200**
   - Request Headers 应该包含 `Authorization: Bearer xxx`
   - Response 应该返回更新后的文章数据

## 技术细节

### Token 刷新流程

```
1. 用户操作 → API 请求
2. 后端返回 401
3. 前端拦截器捕获 401
4. 使用 refresh token 请求新的 access token
5. 如果成功：
   - 更新 localStorage
   - 重试原请求
6. 如果失败：
   - 清除认证状态
   - 跳转登录页
```

### Token 结构

```json
{
  "sub": "user_id",
  "email": "user@example.com",
  "active_tenant_id": "tenant_uuid",
  "type": "access",
  "exp": 1720000000,
  "iat": 1719999100
}
```

## 需要帮助？

如果以上方法都无效，请提供：

1. 浏览器控制台的完整错误信息
2. Network 标签中 PATCH 请求的详细信息（Request/Response Headers）
3. `debug-auth.html` 页面显示的 Token 信息
