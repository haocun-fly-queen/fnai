# 支持多个微信公众号配置

## 🎯 功能说明

现在一个租户可以配置多个微信公众号了！

### 修改前
- ❌ 每个租户只能配置一个微信公众号
- ❌ 发布时只能发布到唯一的那个公众号

### 修改后
- ✅ 每个租户可以配置多个微信公众号
- ✅ 发布时可以选择发布到哪个公众号
- ✅ 支持测试号和正式号共存

---

## 📝 修改内容

### 后端修改

#### 1. 创建配置端点 (`wechat_mp.py`)
- 移除"每个租户只能一个配置"的限制
- 改为检查同一租户下 `app_id` 不能重复
- 允许创建多个配置

```python
# 修改前：检查是否已存在，有则报错
existing = await _get_wechat_config(db, tenant_id)
if existing:
    raise HTTPException(status_code=409, detail="已存在配置")

# 修改后：只检查 app_id 是否重复
for config in existing_configs:
    if config.config.get("app_id") == request.app_id:
        raise HTTPException(status_code=409, detail=f"该 App ID 已存在")
```

#### 2. 发布端点 (`wechat_mp.py`)
- 不再自动获取唯一的配置
- 改为从请求参数中获取 `config_id`
- 根据 `config_id` 查询对应的配置

```python
# 修改前：自动获取租户的唯一配置
wechat_config = await _get_wechat_config(db, tenant_id)

# 修改后：根据请求参数获取指定配置
stmt = select(PublishTarget).where(
    PublishTarget.id == request.config_id,
    PublishTarget.tenant_id == tenant_id,
)
wechat_config = result.scalar_one_or_none()
```

#### 3. Schema 修改 (`wechat.py`)
- 添加 `config_id` 字段到 `WechatPublishRequest`

```python
class WechatPublishRequest(BaseModel):
    config_id: UUID  # 新增：选择哪个公众号配置
    author: Optional[str]
    digest: Optional[str]
    ...
```

### 前端修改

#### 1. 类型定义 (`publish-api.ts`)
- 添加 `config_id` 字段

```typescript
export interface WechatPublishRequest {
  article_id: string;
  config_id: string;  // 新增
  author?: string;
  digest?: string;
}
```

#### 2. 发布对话框 (`PublishDialog.tsx`)
- 添加 `selectedWechatId` 状态
- 添加选择公众号的下拉框
- 发布时传递 `config_id`

```typescript
// 新增状态
const [selectedWechatId, setSelectedWechatId] = useState('');

// 自动选择第一个配置
if (wechatData.length > 0 && wechatData[0]) {
  setSelectedWechatId(wechatData[0].id);
}

// 发布时传递 config_id
await publishToWechat({
  article_id: articleId,
  config_id: selectedWechatId,  // 新增
  author: wechatAuthor || undefined,
  digest: wechatDigest || undefined,
});
```

#### 3. UI 变化
将固定显示第一个配置改为下拉选择框：

```tsx
{/* 修改前：固定显示 */}
<div className="rounded-lg border border-green-200 bg-green-50 p-3">
  <div className="text-sm font-medium text-green-800">
    公众号：{wechatConfigs[0]?.name}
  </div>
</div>

{/* 修改后：下拉选择 */}
<select
  value={selectedWechatId}
  onChange={(e) => setSelectedWechatId(e.target.value)}
>
  {wechatConfigs.map((config) => (
    <option key={config.id} value={config.id}>
      {config.name}
    </option>
  ))}
</select>
```

---

## 🚀 使用指南

### 1. 配置多个公众号

**场景**：同时配置测试号和正式号

1. 进入"发布目标管理" → "微信公众号配置"
2. 点击"添加配置"
3. 配置测试号：
   - 名称：测试公众号
   - App ID：测试号的 appID
   - App Secret：测试号的 appsecret
4. 再次点击"添加配置"
5. 配置正式号：
   - 名称：正式公众号
   - App ID：正式号的 appID
   - App Secret：正式号的 appsecret

### 2. 发布文章

1. 打开文章编辑页
2. 点击"发布到微信公众号"
3. **选择要发布的公众号**（下拉框）
4. 填写作者和摘要（可选）
5. 点击发布

---

## 📊 常见场景

### 场景 1: 测试后正式发布

```
1. 配置测试号和正式号
2. 先发布到测试号验证
3. 确认无误后发布到正式号
```

### 场景 2: 多个公众号同时发布

```
1. 配置多个正式公众号
2. 发布文章时选择第一个公众号
3. 再次发布，选择第二个公众号
4. 一篇文章可以发布到多个公众号
```

### 场景 3: 区分不同用途的公众号

```
1. 技术公众号（App ID: xxx1）
2. 营销公众号（App ID: xxx2）
3. 内部测试号（App ID: xxx3）

根据文章类型选择对应的公众号发布
```

---

## ⚠️ 注意事项

### 1. App ID 不能重复

同一租户下，不能添加相同 `app_id` 的配置。

**错误示例**：
```
配置A：测试公众号 - App ID: wx123
配置B：正式公众号 - App ID: wx123  ❌ 报错：该 App ID 已存在
```

### 2. 必须选择公众号

发布时如果没有选择公众号，会提示错误。

### 3. 不同公众号的 IP 白名单

如果使用正式公众号，每个公众号都需要单独配置 IP 白名单。

### 4. 配置名称建议

建议使用清晰的名称区分不同公众号：
- ✅ "测试公众号 - 开发环境"
- ✅ "正式公众号 - FNAI技术博客"
- ❌ "公众号1"（不清晰）

---

## 🧪 测试验证

### 测试步骤

1. **添加两个配置**
   ```
   配置1：测试公众号
   配置2：正式公众号（或另一个测试号）
   ```

2. **验证列表显示**
   - 刷新页面
   - 进入"发布目标管理"
   - 应该看到两个配置

3. **测试发布**
   - 创建一篇测试文章
   - 点击"发布到微信公众号"
   - 下拉框应该显示两个选项
   - 选择"测试公众号"发布
   - 验证发布成功

4. **再次发布到另一个号**
   - 同一篇文章
   - 再次点击"发布到微信公众号"
   - 选择"正式公众号"
   - 验证可以发布到第二个公众号

---

## 🔄 数据库影响

### 无需迁移

此功能不需要数据库迁移：
- ✅ 使用现有的 `publish_targets` 表
- ✅ 无新增字段
- ✅ 无表结构变化
- ✅ 现有数据完全兼容

### 数据存储

```sql
-- publish_targets 表
SELECT 
  id,
  tenant_id,
  name,
  type,
  config ->> 'app_id' as app_id
FROM publish_targets
WHERE type = 'wechat_mp'
  AND tenant_id = 'xxx';

-- 结果示例
id                  | name         | app_id
--------------------|--------------|--------
uuid-1              | 测试公众号   | wx123
uuid-2              | 正式公众号   | wx456
```

---

## 🐛 已知问题和限制

### 限制

1. **同一租户下 app_id 不能重复**
   - 合理限制，同一个公众号不需要配置两次

2. **发布记录关联配置 ID**
   - `publish_logs.target_id` 指向具体的配置
   - 删除配置不会删除历史发布记录

### 未来优化

1. **批量发布**
   - 一次发布到多个公众号
   - 勾选多个配置

2. **默认公众号**
   - 标记一个配置为默认
   - 发布时自动选中

3. **公众号标签**
   - 给配置打标签（测试/正式/技术/营销）
   - 按标签筛选

---

## 📞 常见问题

### Q1: 已有的旧配置会受影响吗？

A: 不会。旧配置完全兼容，会作为第一个配置自动选中。

### Q2: 如何删除不用的配置？

A: 进入"发布目标管理" → 找到对应配置 → 点击删除

### Q3: 删除配置会影响历史发布记录吗？

A: 不会。历史发布记录保留，但无法再次发布到已删除的配置。

### Q4: 可以配置无限个公众号吗？

A: 技术上可以，但建议不超过 10 个，便于管理。

---

**功能已完成，可以使用了！** 🎉
