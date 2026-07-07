# 发布状态简化说明

## 修改时间
2026-07-07

## 修改目标
简化发布日志 API 响应，只返回用户真正需要的信息：
- 是否已发布（布尔值）
- 发布时间
- 发布目标名称

## 修改内容

### 1. 新增简化版 Schema
**文件**: `backend/app/schemas/publish.py`

新增 `PublishLogSimpleResponse`:
```python
class PublishLogSimpleResponse(BaseModel):
    """发布日志响应体（简化版）—— 只返回是否已发布和发布时间。"""

    is_published: bool = Field(..., description="是否已发布成功")
    published_at: datetime = Field(..., description="发布时间（包括失败的尝试）")
    target_name: str = Field(..., description="发布目标名称（如'微信公众号'）")
```

### 2. 更新 API 端点
**文件**: `backend/app/api/v1/publish.py`

**端点**: `GET /api/v1/articles/{article_id}/publish-logs`

**修改前**:
```json
[
  {
    "id": "uuid",
    "article_id": "uuid",
    "target_id": "uuid",
    "status": "pending",
    "remote_id": "123",
    "error_message": null,
    "published_at": "2026-07-07T02:38:18",
    "created_by": "uuid",
    "target_name": "测试公众号",
    "article_title": "文章标题"
  }
]
```

**修改后**:
```json
[
  {
    "is_published": false,
    "published_at": "2026-07-07T02:38:18",
    "target_name": "测试公众号"
  }
]
```

### 3. 更新测试脚本

**test_wechat_publish.py** (异步版):
```python
for log in logs[:3]:
    status = "✅ 已发布" if log['is_published'] else "❌ 未发布"
    print(f"  - {log['target_name']}: {status} @ {log['published_at'][:19]}")
```

**test_wechat_publish2.py** (同步版):
```python
for log in logs[:3]:
    status = "✅ 已发布" if log.get('is_published') else "❌ 未发布"
    print(f"  - {log.get('target_name', '?')}: {status} @ {log.get('published_at', '?')[:19]}")
```

## 测试结果

### 测试 1 (test_wechat_publish.py)
```
=== 查询发布日志 ===
✅ 共 1 条发布记录
  - 测试公众号: ❌ 未发布 @ 2026-07-07T02:38:18
```

### 测试 2 (test_wechat_publish2.py)
```
[Step 6] Check publish logs...
OK - 2 publish log(s)
  - 测试公众号: ❌ 未发布 @ 2026-07-07T02:38:35
  - 测试公众号: ❌ 未发布 @ 2026-07-07T02:38:18
```

## 向后兼容性

- **数据库模型**: 未修改，完全向后兼容
- **旧的 Schema**: `PublishLogResponse` 保留，供需要详细信息的场景使用
- **新的 Schema**: `PublishLogSimpleResponse` 用于前端展示

## 前端影响

前端需要更新调用 `/api/v1/articles/{article_id}/publish-logs` 的代码：

**修改前**:
```typescript
interface PublishLog {
  id: string;
  status: 'pending' | 'success' | 'failed';
  target_name?: string;
  published_at: string;
  // ... 其他字段
}
```

**修改后**:
```typescript
interface PublishLog {
  is_published: boolean;
  published_at: string;
  target_name: string;
}
```

## 优势

1. **响应更简洁** - 减少 70% 的字段数量（从 10 个减少到 3 个）
2. **更易理解** - `is_published` 比 `status: 'success'` 更直观
3. **性能优化** - 更小的响应体积，更快的传输速度
4. **前端友好** - 不需要复杂的状态映射逻辑

## 后续建议

1. 考虑在前端添加"查看详情"功能，需要详细错误信息时可以调用完整版 API
2. 可以考虑为其他资源（如素材、标签等）也提供类似的简化响应
