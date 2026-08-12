# 401 错误排查和修复指南

## 问题症状

```
GET http://localhost:5173/api/v1/invitations 401 (Unauthorized)
GET http://localhost:5173/api/v1/auth/me 401 (Unauthorized)
```

点击按钮时出现这些错误。

---

## 🔍 原因分析

### 1. Token 过期（最常见）
- Access Token 默认 15 分钟过期
- 如果你很久没重新登录，token 会失效

### 2. activeTenantId 缺失
- 虽然我们修复了登录逻辑
- 但你可能还在使用旧的 localStorage 数据

### 3. 前端代码未更新
- 代码更新后前端未重新编译
- 浏览器缓存了旧版本

---

## ✅ 解决方案

### 方案 A: 一键修复（最推荐）⭐⭐⭐⭐⭐

**步骤**:
1. 按 `F12` 打开浏览器控制台
2. 切换到 `Console` 标签
3. 复制粘贴以下代码并回车：

```javascript
// 清除旧的认证信息
localStorage.removeItem('fnai.auth');
console.log('✅ 已清除认证信息');

// 刷新页面
location.reload();
```

4. 页面刷新后重新登录

**为什么有效**:
- 清除了可能过期或格式错误的认证数据
- 重新登录会使用新的代码逻辑（包含 activeTenantId 修复）

---

### 方案 B: 检查并修复

如果想确认具体问题，按以下步骤操作：

#### 步骤 1: 检查 localStorage

在浏览器控制台执行：

```javascript
const auth = JSON.parse(localStorage.getItem('fnai.auth'));
console.log('完整数据:', auth);
console.log('Token:', auth?.state?.accessToken || auth?.accessToken);
console.log('Tenant ID:', auth?.state?.activeTenantId || auth?.activeTenantId);
```

**检查结果**:
- 如果 `Token` 显示 `undefined` → Token 缺失，需要重新登录
- 如果 `Tenant ID` 显示 `undefined` → **这就是问题所在**

#### 步骤 2: 检查 Token 是否过期

```javascript
const auth = JSON.parse(localStorage.getItem('fnai.auth'));
const token = auth?.state?.accessToken || auth?.accessToken;

if (token) {
    const parts = token.split('.');
    const payload = JSON.parse(atob(parts[1]));
    
    const now = Math.floor(Date.now() / 1000);
    const exp = payload.exp;
    
    console.log('当前时间:', new Date(now * 1000).toLocaleString());
    console.log('过期时间:', new Date(exp * 1000).toLocaleString());
    console.log('是否过期:', exp < now ? '❌ 已过期' : '✅ 有效');
    console.log('剩余时间:', Math.floor((exp - now) / 60), '分钟');
}
```

**检查结果**:
- 如果显示 `❌ 已过期` → Token 过期，需要重新登录

#### 步骤 3: 手动添加 activeTenantId（临时方案）

如果只是缺少 `activeTenantId`，可以手动添加：

```javascript
const auth = JSON.parse(localStorage.getItem('fnai.auth'));

// 从 memberships 中获取第一个租户 ID
const tenantId = auth.state?.memberships?.[0]?.tenant?.id || 
                 auth.memberships?.[0]?.tenant?.id;

if (tenantId) {
    // 添加 activeTenantId
    if (auth.state) {
        auth.state.activeTenantId = tenantId;
    } else {
        auth.activeTenantId = tenantId;
    }
    
    // 保存回 localStorage
    localStorage.setItem('fnai.auth', JSON.stringify(auth));
    
    console.log('✅ 已添加 activeTenantId:', tenantId);
    console.log('刷新页面生效');
    
    // 刷新页面
    location.reload();
} else {
    console.log('❌ 未找到租户信息，请重新登录');
}
```

---

### 方案 C: 重启前端服务

代码更新后需要重启：

```bash
# 1. 停止前端（Ctrl+C）

# 2. 清除缓存（可选）
cd fnai-monorepo/frontend
rm -rf node_modules/.vite

# 3. 重新启动
npm run dev
```

---

## 🔄 完整修复流程

### 流程图

```
1. 清除 localStorage
   ↓
2. 刷新页面
   ↓
3. 重新登录
   ↓
4. 检查是否还有错误
   ↓
5. 如果还有 → 重启前端服务
```

### 详细步骤

```javascript
// === 步骤 1: 在浏览器控制台执行 ===
localStorage.removeItem('fnai.auth');
location.reload();

// === 步骤 2: 页面刷新后 ===
// 点击"登录"，输入账号密码

// === 步骤 3: 登录后检查 ===
const auth = JSON.parse(localStorage.getItem('fnai.auth'));
console.log('activeTenantId:', auth?.state?.activeTenantId);
// 应该显示一个 UUID，不是 undefined

// === 步骤 4: 测试功能 ===
// 尝试点击之前报错的按钮
```

---

## 🛠️ 预防措施

### 1. 定期清理过期数据

在应用启动时检查 Token 是否过期：

```typescript
// App.tsx 或主组件
useEffect(() => {
  const auth = localStorage.getItem('fnai.auth');
  if (auth) {
    try {
      const parsed = JSON.parse(auth);
      const token = parsed.state?.accessToken || parsed.accessToken;
      
      if (token) {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const isExpired = payload.exp < Math.floor(Date.now() / 1000);
        
        if (isExpired) {
          // Token 已过期，清除
          localStorage.removeItem('fnai.auth');
          window.location.href = '/login';
        }
      }
    } catch (e) {
      // 数据格式错误，清除
      localStorage.removeItem('fnai.auth');
    }
  }
}, []);
```

### 2. 自动刷新 Token

在 `api.ts` 拦截器中已经实现了自动刷新，但如果 refresh token 也过期了，会自动跳转登录。

### 3. 显示 Token 过期提示

```typescript
// 在 API 拦截器中
if (err.response?.status === 401) {
  // 显示友好提示
  alert('登录已过期，请重新登录');
  localStorage.removeItem('fnai.auth');
  window.location.href = '/login';
}
```

---

## 📊 常见场景

### 场景 1: 刚登录就 401

**原因**: 登录时没有设置 `activeTenantId`

**解决**: 
- 确认使用的是最新代码
- 清除 localStorage 重新登录

### 场景 2: 使用一段时间后 401

**原因**: Token 过期（15 分钟）

**解决**:
- 正常情况会自动刷新
- 如果 refresh token 也过期（7 天），需要重新登录

### 场景 3: 刷新页面后 401

**原因**: localStorage 数据损坏

**解决**:
- 清除 localStorage
- 重新登录

---

## 🧪 测试验证

### 完整测试流程

```javascript
// 1. 清除旧数据
localStorage.clear();
location.reload();

// 2. 重新登录
// (在登录页面操作)

// 3. 登录成功后检查
const auth = JSON.parse(localStorage.getItem('fnai.auth'));
console.log('✅ 检查清单:');
console.log('Token 存在?', !!(auth?.state?.accessToken || auth?.accessToken));
console.log('Tenant ID 存在?', !!(auth?.state?.activeTenantId || auth?.activeTenantId));
console.log('Memberships 存在?', !!(auth?.state?.memberships || auth?.memberships));

// 4. 测试 API
fetch('/api/v1/auth/me', {
    headers: {
        'Authorization': `Bearer ${auth.state?.accessToken || auth.accessToken}`,
        'X-Tenant-Id': auth.state?.activeTenantId || auth.activeTenantId
    }
}).then(r => {
    console.log('API 测试结果:', r.status === 200 ? '✅ 成功' : '❌ 失败');
    return r.json();
}).then(data => {
    console.log('用户数据:', data);
});
```

---

## 💡 快速命令

### 在浏览器控制台直接复制粘贴

```javascript
// 一键修复
localStorage.removeItem('fnai.auth');
alert('已清除认证信息，页面即将刷新，请重新登录');
location.reload();
```

### 检查当前状态

```javascript
// 快速检查
(function() {
    const auth = localStorage.getItem('fnai.auth');
    if (!auth) {
        console.log('❌ 未登录');
        return;
    }
    
    const parsed = JSON.parse(auth);
    const token = parsed?.state?.accessToken || parsed?.accessToken;
    const tenantId = parsed?.state?.activeTenantId || parsed?.activeTenantId;
    
    console.log('Token:', token ? '✅ 存在' : '❌ 缺失');
    console.log('Tenant ID:', tenantId ? '✅ 存在' : '❌ 缺失');
    
    if (token) {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const isExpired = payload.exp < Math.floor(Date.now() / 1000);
        console.log('Token 状态:', isExpired ? '❌ 已过期' : '✅ 有效');
    }
})();
```

---

## 📞 还是不行？

如果以上方法都不行，可能是：

1. **后端未启动** - 检查 `http://localhost:8000/docs`
2. **数据库连接失败** - 检查后端日志
3. **代码版本不一致** - 确认拉取了最新代码

### 终极解决方案

```bash
# 1. 停止所有服务

# 2. 拉取最新代码
cd fnai-monorepo
git pull origin feat/phase3-celery-and-search

# 3. 重新启动后端
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload

# 4. 重新启动前端
cd ../frontend
npm run dev

# 5. 浏览器清除缓存
# Ctrl+Shift+Delete → 清除缓存

# 6. 重新登录
```

---

**问题解决了记得告诉我！** 🎉
