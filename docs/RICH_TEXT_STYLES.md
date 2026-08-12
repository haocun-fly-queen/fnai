# 富文本样式增强 - 方案 B 实施说明

## 问题背景

用户反馈发布到微信公众号和微博时，文章的字体样式格式丢失。

**根本原因**:
1. AI 生成的 HTML 只有语义标签(`<h1>`, `<p>`, `<strong>`)，没有样式属性
2. 微博发布时直接剥离所有 HTML 标签，变成纯文本

## 解决方案 (方案 B: 富文本编辑器方案)

### 核心思路
1. **AI 生成**: Markdown → HTML 时添加丰富的内联样式
2. **用户编辑**: TipTap 编辑器保留和增强样式
3. **数据存储**: `article.content` 存带完整内联样式的 HTML
4. **多平台发布**: 
   - 微信公众号/WordPress: 直接用带样式的 HTML ✅
   - 微博: 剥离标签变纯文本(平台限制，无法避免) ⚠️

## 实施改动

### 1. 后端 - 样式增强 (`backend/app/services/generation.py`)

#### 新增函数 `_add_rich_text_styles()`
为 HTML 添加内联样式，兼容微信公众号要求:

**支持的样式**:
- **标题** (h1/h2/h3): 字号、颜色、间距、边框装饰
- **段落**: 字号 16px、行距 1.8、两端对齐
- **列表**: 缩进、项目符号样式
- **粗体/斜体**: 颜色强化 (#2c3e50 / #7f8c8d)
- **引用块**: 灰色背景 + 左边框
- **代码块**: 灰色背景 + 圆角
- **表格**: 边框、单元格样式
- **图片**: 响应式、居中显示

#### 生成流程修改 (第 207-210 行)
```python
# 转 HTML 并添加富文本样式
html = md_lib.markdown(cleaned, extensions=["extra", "nl2br"])
article.content = _add_rich_text_styles(html)
```

### 2. 数据模型 - 注释更新 (`backend/app/models/article.py`)

```python
# 正文（富文本 HTML，带内联样式）
# AI 生成时从 Markdown 转换并添加样式；用户编辑时由前端富文本编辑器生成
content: Mapped[str] = mapped_column(Text, nullable=False, default="")
```

### 3. 依赖 - 新增 BeautifulSoup4 (`backend/requirements.txt`)

```
beautifulsoup4==4.12.3
```

用于 HTML 解析和样式注入。

### 4. 前端 - 已就绪

TipTap 编辑器已配置样式扩展:
- `TextStyle`: 文本样式支持
- `Color`: 颜色选择
- `FontSize`: 字号调整

保存时用 `editor.getHTML()` 保留完整样式。

## 效果对比

### 微信公众号

**改动前**:
```html
<h2>章节标题</h2>
<p>这是一段<strong>粗体</strong>文字。</p>
```
→ 微信显示: 无样式，依赖主题 CSS(可能不生效)

**改动后**:
```html
<h2 style="font-size: 20px; font-weight: bold; color: #34495e; padding-left: 10px; border-left: 4px solid #3498db;">章节标题</h2>
<p style="font-size: 16px; color: #3f3f3f; line-height: 1.8;">这是一段<strong style="font-weight: bold; color: #2c3e50;">粗体</strong>文字。</p>
```
→ 微信显示: ✅ 有字号、颜色、行距、边框装饰

### 微博

**改动前/后 - 无变化**:
微博不支持 HTML，发布时会剥离所有标签:
```python
text = re.sub(r"<[^>]+>", "", article.content)  # weibo.py:49
```

**结果**: ⚠️ 微博只能是纯文本，无法保留格式(平台限制)

可能的改进:
- 用 Markdown 文本标记(`**粗体**`, `## 标题`)
- 发布为图片(渲染成图片后上传)

### WordPress

**效果**: ✅ 内联样式会保留，即使主题 CSS 缺失也有基础格式

## 验证步骤

### 1. 安装依赖
```bash
cd backend
pip install beautifulsoup4==4.12.3
```

### 2. 重启后端服务
```bash
# 如果已在运行，重启以加载新代码
```

### 3. 测试生成文章
1. 创建新文章并触发 AI 生成
2. 生成完成后，查看 `article.content` 字段，应包含大量 `style=` 属性
3. 在前端编辑器打开，样式应正常显示

### 4. 测试发布
- **微信公众号**: 发布后在微信后台查看，标题、段落应有明显样式差异
- **微博**: 发布后是纯文本(符合预期)
- **WordPress**: 发布后前台查看，应有格式

## 扩展性

### 新增平台
- **支持 HTML**: 直接用 `article.content`，样式开箱即用 ✅
- **仅支持纯文本**: 需自行剥离标签或转换格式

### 样式自定义
修改 `_add_rich_text_styles()` 函数中的样式定义:
```python
# 例如:调整标题字号
for h2 in soup.find_all('h2'):
    h2['style'] = 'font-size: 22px; ...'  # 改为 22px
```

### 用户自定义样式
前端 TipTap 编辑器已支持:
- 字号选择
- 颜色选择  
- 对齐方式
- 加粗/斜体/下划线

用户在编辑器中设置的样式会保留到 HTML，发布时生效。

## 注意事项

1. **微信公众号样式限制**: 不支持所有 CSS 属性，复杂样式可能被过滤
2. **微博无样式**: 这是平台限制，无法通过代码解决
3. **图片样式**: `_add_rich_text_styles()` 已给图片添加响应式样式(max-width: 100%)
4. **兼容性**: 内联样式兼容性最好，几乎所有富文本平台都支持

## 后续优化

### 短期
- [ ] 为微博生成更友好的纯文本格式(用空行、序号优化排版)
- [ ] 添加样式预设(多种风格供用户选择)

### 长期
- [ ] 微博图片发布(将文章渲染成图片)
- [ ] 用户自定义样式模板
- [ ] 平台特定样式优化(针对微信/WordPress 单独调整)

## 相关文件

- `backend/app/services/generation.py` - 样式增强逻辑
- `backend/app/models/article.py` - 数据模型注释
- `backend/app/services/publishers/wechat_mp.py` - 微信发布
- `backend/app/services/publishers/weibo.py` - 微博发布
- `frontend/src/pages/ArticleEditorPage.tsx` - TipTap 编辑器配置

---

**实施日期**: 2026-07-13  
**实施人**: Claude (Kiro)  
**测试状态**: 待测试
