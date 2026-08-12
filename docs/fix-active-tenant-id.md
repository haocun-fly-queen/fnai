# 修复 401 错误 - activeTenantId 缺失问题

## 问题根因

**症状**: 登录后所有 API 请求都返回 401 Unauthorized

**根本原因**: 登录/注册后没有设置 `activeTenantId`，导致后端权限检查失败

## 技术细节

### 后端权限检查流程

```python
# backend/app/api/v1/deps.py

async def get_active_tenant_id(creds) -> UUID | None:
    """从 access token 的 payload 里拿 active_tenant_id"""
    payload = decode_token(creds.credentials, expected_type="access")
    tid = payload.get("active_tenant_id")  # ← 这个值必须存在
    return UUID(tid) if tid else None

def require_role(min_role: Role):
    async def checker(user, tenant_id, db) -> TenantMember:
        # 检查 1: 必须有激活的租户
        if tenant_id is None:
            raise HTTPException(
                status_code=400,
                detail="No active tenant"  # ← 这里会导致 401
            )
        # ... 其他检查
```

### 前端问题代码

**修改前** (LoginPage.tsx):
```typescript
// ❌ 缺少 activeTenantId
setSession({
  accessToken: tokens.access_token,
  refreshToken: tokens.refresh_token,
  user: { ... },
  memberships: me.memberships,
  // activeTenantId 缺失！
});
```

**修改后**:
```typescript
// ✅ 自动选择第一个租户
let activeTenantId: string | undefined;
if (me.memberships.length > 0) {
  const ownerMembership = me.memberships.find((m) => m.role === 'owner');
  activeTenantId = ownerMembership?.tenant.id || me.memberships[0].tenant.id;
}

setSession({
  accessToken: tokens.access_token,
  refreshToken: tokens.refresh_token,
  user: { ... },
  memberships: me.memberships,
  activeTenantId,  // ✅ 设置激活租户
});
```

## 修复内容

### 1. LoginPage.tsx
- ✅ 登录成功后自动选择第一个 OWNER 租户
- ✅ 如果没有 OWNER 租户，选择第一个租户
- ✅ 设置 `activeTenantId` 到 localStorage

### 2. RegisterPage.tsx
- ✅ 注册成功后自动选择新创建的租户
- ✅ 设置 `activeTenantId` 到 localStorage

## 验证修复

### 步骤 1: 清除旧数据
```javascript
// 在浏览器控制台执行
localStorage.removeItem('fnai.auth');
location.reload();
```

### 步骤 2: 重新登录
1. 访问 `/login`
2. 输入邮箱和密码
3. 点击登录

### 步骤 3: 检查状态
打开浏览器控制台，执行：
```javascript
const auth = JSON.parse(localStorage.getItem('fnai.auth'));
console.log('activeTenantId:', auth.state?.activeTenantId || auth.activeTenantId);
console.log('memberships:', auth.state?.memberships || auth.memberships);
```

**预期输出**:
```
activeTenantId: "550e8400-e29b-41d4-a716-446655440000"
memberships: [{tenant: {id: "...", name: "..."}, role: "owner"}]
```

### 步骤 4: 测试 API
1. 访问 `/articles` 页面
2. 应该能正常加载文章列表
3. 打开 Network 标签，检查请求头：
   - `Authorization: Bearer xxx` ✅
   - `X-Tenant-Id: xxx` ✅

## 相关文件

### 前端
- `frontend/src/pages/LoginPage.tsx` - 登录页面
- `frontend/src/pages/RegisterPage.tsx` - 注册页面
- `frontend/src/stores/auth.ts` - 认证状态管理
- `frontend/src/lib/api.ts` - Axios 拦截器

### 后端
- `backend/app/api/v1/deps.py` - 权限依赖注入
- `backend/app/core/security.py` - Token 编解码

## 为什么需要 activeTenantId？

### 多租户架构
FNAI 采用多租户架构，一个用户可以属于多个租户（工作空间）：

```
User A
├── Tenant 1 (公司 A) - Role: OWNER
├── Tenant 2 (公司 B) - Role: MEMBER
└── Tenant 3 (个人空间) - Role: OWNER
```

### 权限隔离
- 用户在不同租户中有不同的权限
- API 请求必须明确"当前在哪个租户下操作"
- 防止数据泄露和越权访问

### Token 中的 activeTenantId
```json
{
  "sub": "user_id",
  "email": "user@example.com",
  "active_tenant_id": "tenant_uuid",  // ← 当前激活的租户
  "type": "access",
  "exp": 1720000000
}
```

## 切换租户

用户可以在多个租户之间切换：

```typescript
// frontend/src/components/TenantSwitcher.tsx (示例)
const switchTenant = async (tenantId: string) => {
  // 调用后端 API 切换租户，获取新的 token
  const tokens = await switchActiveTenant(tenantId);
  
  // 更新本地状态
  switchActiveTenant({
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    activeTenantId: tenantId,
  });
};
```

## 常见问题

### Q: 为什么不在登录时直接返回 activeTenantId？
A: 因为用户可能属于多个租户，后端无法决定默认选择哪个。前端根据业务逻辑自动选择（优先 OWNER 角色）。

### Q: 如果用户没有任何租户会怎样？
A: 注册时会自动创建一个租户，所以正常情况下不会出现。如果出现，应该引导用户创建或加入租户。

### Q: activeTenantId 存储在哪里？
A: 
1. **localStorage** - 持久化存储（刷新页面后保留）
2. **Token payload** - 每次请求都会验证
3. **Zustand store** - 运行时状态管理

### Q: 切换租户后需要重新登录吗？
A: 不需要，调用切换 API 后会返回新的 token（包含新的 activeTenantId），前端更新 localStorage 即可。

## 安全性

### Token 校验
后端每次请求都会：
1. 验证 token 签名和有效期
2. 检查 token 中的 `active_tenant_id`
3. 查询数据库确认用户是该租户的成员
4. 验证用户在该租户中的角色权限

### 防止越权
即使前端篡改 `X-Tenant-Id` 头，后端也会：
1. 忽略 header 中的值
2. 只信任 token 中的 `active_tenant_id`
3. 查询数据库二次验证

## 后续优化建议

### 1. 添加租户切换器 UI
在顶部导航栏添加租户下拉选择器

### 2. 记住用户的租户偏好
```typescript
// 记住用户最后使用的租户
localStorage.setItem('last_tenant_id', activeTenantId);

// 下次登录时自动选择
const lastTenantId = localStorage.getItem('last_tenant_id');
if (lastTenantId && memberships.some(m => m.tenant.id === lastTenantId)) {
  activeTenantId = lastTenantId;
}
```

### 3. 租户上下文提示
在 UI 上显示当前所在的租户，避免用户混淆

### 4. 无租户时的引导流程
```typescript
if (me.memberships.length === 0) {
  // 引导用户创建租户或等待邀请
  navigate('/onboarding');
}
```

## 测试清单

- [ ] 登录后能正常访问文章列表
- [ ] 登录后能保存文章
- [ ] 注册后能正常访问 Dashboard
- [ ] 刷新页面后状态保持
- [ ] localStorage 中有 `activeTenantId`
- [ ] Network 请求头包含 `X-Tenant-Id`
- [ ] 控制台无 401 错误

## 回滚计划

如果修复后仍有问题：

1. 检查后端日志：
   ```bash
   tail -f backend/logs/app.log | grep "401\|active_tenant"
   ```

2. 验证数据库：
   ```sql
   SELECT * FROM tenant_members WHERE user_id = 'xxx';
   ```

3. 临时回滚：
   ```bash
   git checkout HEAD~1 frontend/src/pages/LoginPage.tsx
   git checkout HEAD~1 frontend/src/pages/RegisterPage.tsx
   ```
