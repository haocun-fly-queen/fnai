# 微信发布状态自动更新功能

## 问题描述

用户反馈：
1. **发布成功后仍显示"未发布"** - 数据库状态是 `PENDING`，没有更新为 `SUCCESS`
2. **时间不正确** - 显示的是提交时间，不是实际发布时间

## 根本原因

微信公众号发布是**异步流程**：

```
1. 提交发布 → 返回 publish_id
2. 微信后台审核（可能几秒到几分钟）
3. 审核通过 → 自动发布
```

**原有逻辑**：
- 提交后状态设为 `PENDING`
- 没有自动查询和更新最终状态
- 需要用户手动轮询或永远停留在 `PENDING`

## 解决方案

### 方案：查询时自动更新状态

在 `GET /api/v1/articles/{id}/publish-logs` 端点中：
1. 查询发布日志
2. 对于微信发布且状态为 `PENDING` 的记录
3. 自动调用微信 API 查询最新状态
4. 更新数据库状态和时间
5. 返回最新结果

### 实现细节

**文件**: `backend/app/api/v1/publish.py`

```python
@router.get("/articles/{article_id}/publish-logs")
async def get_publish_logs(...):
    """查看文章的发布历史（简化版）。
    
    会自动更新微信发布的状态（如果是待审核状态）。
    """
    
    # 查询发布日志
    rows = await db.execute(...)
    
    # 对于微信发布且状态为 PENDING 的记录，尝试更新状态
    for log, target in rows:
        if (
            target.type == PublishTargetType.WECHAT_MP
            and log.status == PublishStatus.PENDING
            and log.remote_id
        ):
            try:
                client = WechatMpClient(...)
                status_data = await client.get_publish_status(log.remote_id)
                wechat_status = status_data.get("publish_status", 1)
                
                # 微信发布状态：0/3 = 成功，2 = 失败，1 = 审核中
                if wechat_status in (0, 3):
                    log.status = PublishStatus.SUCCESS
                    log.published_at = datetime.utcnow()  # 更新为实际发布时间
                    await db.commit()
                elif wechat_status == 2:
                    log.status = PublishStatus.FAILED
                    log.error_message = status_data.get("fail_reason")
                    await db.commit()
            except Exception as e:
                logger.warning(f"Failed to update wechat status: {e}")
                # 失败不影响返回结果
```

### 微信发布状态码

| 状态码 | 含义 | 映射 |
|-------|------|------|
| 0 | 成功 | SUCCESS |
| 1 | 审核中 | PENDING |
| 2 | 审核失败 | FAILED |
| 3 | 已发表 | SUCCESS |

## 优势

### ✅ 自动化
- 无需用户手动刷新
- 前端每次查询都能获取最新状态
- 不需要额外的轮询逻辑

### ✅ 即时性
- 用户刷新页面即可看到最新状态
- 适合低频查询场景（查看发布历史）

### ✅ 简单可靠
- 只在查询时更新，不增加系统负担
- 更新失败不影响返回结果
- 无需额外的定时任务

## 使用场景

### 场景 1：发布后立即查看
```
1. 用户点击"发布到微信"
2. 提交成功，状态显示"未发布"（PENDING）
3. 用户等待 5-10 秒
4. 刷新页面或重新打开文章
5. 自动查询微信状态并更新
6. 显示"已发布"（SUCCESS）✅
```

### 场景 2：历史记录查询
```
1. 用户打开之前发布的文章
2. 查看发布状态
3. 如果之前是 PENDING，自动更新为最终状态
4. 显示准确的发布结果
```

## 性能考虑

### 查询频率
- **触发条件**：只在查询发布日志时触发
- **查询对象**：只查询状态为 PENDING 的记录
- **API 调用**：每条 PENDING 记录调用一次微信 API

### 优化措施
1. **只更新 PENDING 状态** - 已成功或失败的不再查询
2. **异常处理** - 更新失败不影响返回结果
3. **日志记录** - 记录更新操作，便于排查

### 典型场景分析

**场景 A：正常发布**
- 发布后状态：PENDING
- 用户 10 秒后刷新：调用 1 次微信 API，更新为 SUCCESS
- 后续查询：直接返回 SUCCESS，不再调用 API
- **总 API 调用：1 次**

**场景 B：多次查询**
- 发布后状态：PENDING
- 用户 5 秒后刷新：调用 1 次，仍是 PENDING（审核中）
- 用户 10 秒后刷新：调用 1 次，更新为 SUCCESS
- 后续查询：不再调用 API
- **总 API 调用：2 次**

## 替代方案对比

### 方案 A：定时任务（未采用）
```python
# 每分钟扫描所有 PENDING 状态并更新
@celery.task
def update_pending_wechat_status():
    for log in pending_logs:
        update_status(log)
```

**缺点**：
- 增加系统复杂度
- 需要 Celery 或类似任务队列
- 浪费资源（可能大部分记录无人查询）

### 方案 B：前端轮询（未采用）
```typescript
// 前端每 3 秒查询一次状态
const timer = setInterval(() => {
  checkPublishStatus(publishId);
}, 3000);
```

**缺点**：
- 前端逻辑复杂
- 用户离开页面后无法更新
- 频繁请求浪费带宽

### 方案 C：查询时更新（✅ 已采用）
```python
# 只在用户查询时才更新
async def get_publish_logs(...):
    for log in logs:
        if log.status == PENDING:
            update_status(log)
```

**优点**：
- 简单直观
- 按需更新
- 无需额外组件

## 测试验证

### 测试步骤

1. **发布文章到微信**
   ```bash
   python test_wechat_publish.py
   ```

2. **检查初始状态**
   ```
   [Step 6] Check publish logs...
   OK - 1 publish log(s)
     - 测试公众号: ❌ 未发布 @ 2026-07-07T10:38:18
   ```

3. **等待 10 秒后再次查询**
   ```bash
   curl http://localhost:8000/api/v1/articles/{id}/publish-logs \
     -H "Authorization: Bearer {token}"
   ```

4. **验证状态已更新**
   ```json
   [{
     "is_published": true,
     "published_at": "2026-07-07T10:38:25",
     "target_name": "测试公众号"
   }]
   ```

### 预期结果

- ✅ 状态从 `false` 变为 `true`
- ✅ 时间更新为实际发布时间
- ✅ 前端显示"已发布"

## 注意事项

### 1. 时区问题
- 后端使用 UTC 时间存储
- 前端显示时需要转换为本地时间

### 2. 并发更新
- 使用数据库事务保证一致性
- 同一记录不会被重复更新

### 3. 错误处理
- 微信 API 调用失败不影响查询结果
- 记录日志便于排查问题

### 4. 缓存考虑
- 成功/失败状态不再变化，可以考虑缓存
- PENDING 状态每次都查询

## 监控和日志

### 日志示例
```
INFO: Auto-updated PublishLog abc123 to SUCCESS
WARNING: Failed to update wechat status for log xyz789: timeout
```

### 监控指标
- 微信 API 调用次数
- 更新成功率
- 平均响应时间

## 后续优化

### 1. 批量更新
如果一次查询有多个 PENDING 记录，可以批量调用微信 API

### 2. 缓存优化
对于刚更新的记录，短时间内不再查询

### 3. Webhook 回调
如果微信支持状态变更回调，可以被动接收更新

## 相关文件

- `backend/app/api/v1/publish.py` - 发布日志查询端点
- `backend/app/services/wechat_mp.py` - 微信 API 客户端
- `backend/app/models/publish_log.py` - 发布日志模型
- `backend/app/scripts/update_wechat_status.py` - 手动更新脚本（备用）

## 总结

通过在查询时自动更新微信发布状态，我们实现了：
- ✅ 用户无需手动刷新
- ✅ 状态准确显示
- ✅ 时间正确更新
- ✅ 系统简单可靠

这是一个**按需更新**的解决方案，在简单性和即时性之间取得了良好平衡。
