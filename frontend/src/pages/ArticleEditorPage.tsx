// 文章编辑器页（阶段 4 Step 5.3）—— TipTap 富文本 + 完整工具栏 + 图片样式 + 生成 + 版本 + SEO。
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useEditor, EditorContent, type Editor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Underline from '@tiptap/extension-underline';
import TextAlign from '@tiptap/extension-text-align';
import Highlight from '@tiptap/extension-highlight';
import Link from '@tiptap/extension-link';
import BaseImage from '@tiptap/extension-image';
import { TextStyle } from '@tiptap/extension-text-style';
import { Color } from '@tiptap/extension-color';

// 扩展 Image，增加 style 属性支持（用于对齐等内联样式）
const Image = BaseImage.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      style: {
        default: null,
        parseHTML: (element) => element.getAttribute('style'),
        renderHTML: (attributes) => {
          if (!attributes.style) return {};
          return { style: attributes.style };
        },
      },
    };
  },
});
import {
  getArticle,
  updateArticle,
  generateArticle,
  listVersions,
  saveVersion,
  type ArticleDetail,
  type ArticleVersion,
} from '@/lib/article-api';
import { ExportDialog } from '@/components/ExportDialog';
import { PublishDialog } from '@/components/PublishDialog';

// ---- 工具栏按钮组件 ----
function ToolBtn({
  active,
  onClick,
  label,
  title,
  disabled,
}: {
  active: boolean;
  onClick: () => void;
  label: string | React.ReactNode;
  title: string;
  disabled?: boolean;
}): JSX.Element {
  return (
    <button
      type="button"
      disabled={disabled}
      className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
        active
          ? 'bg-slate-800 text-white'
          : 'text-slate-600 hover:bg-slate-100 disabled:opacity-40'
      }`}
      onClick={onClick}
      title={title}
    >
      {label}
    </button>
  );
}

function Sep(): JSX.Element {
  return <span className="mx-0.5 text-slate-200 select-none">|</span>;
}

// ---- 图片样式面板 ----
function ImageStylePanel({
  editor,
  onClose,
  position,
}: {
  editor: Editor;
  onClose: () => void;
  position: { x: number; y: number };
}): JSX.Element | null {
  const attrs = editor.getAttributes('image');

  // 从 style 字符串解析当前对齐方式（只在初始化时计算）
  const currentStyle: string = attrs.style ?? '';
  const initialAlign = currentStyle.includes('float: left')
    ? 'left'
    : currentStyle.includes('float: right')
      ? 'right'
      : currentStyle.includes('display: block') && currentStyle.includes('margin')
        ? 'center'
        : 'none';

  const [width, setWidth] = useState(attrs.width ?? '');
  const [height, setHeight] = useState(attrs.height ?? '');
  const [alt, setAlt] = useState(attrs.alt ?? '');
  const [align, setAlign] = useState<'none' | 'left' | 'center' | 'right'>(initialAlign);

  const applyChanges = () => {
    const styleParts: string[] = [];
    if (width) styleParts.push(`width: ${width}px`);
    if (height) styleParts.push(`height: ${height}px`);
    if (align === 'left') styleParts.push('float: left', 'margin-right: 12px', 'margin-bottom: 8px');
    else if (align === 'right') styleParts.push('float: right', 'margin-left: 12px', 'margin-bottom: 8px');
    else if (align === 'center') styleParts.push('display: block', 'margin-left: auto', 'margin-right: auto');
    const style = styleParts.length > 0 ? styleParts.join('; ') : undefined;

    editor
      .chain()
      .focus()
      .updateAttributes('image', {
        width: width || null,
        height: height || null,
        alt: alt || null,
        style: style || null,
      })
      .run();
    onClose();
  };

  const deleteImage = () => {
    editor.chain().focus().deleteSelection().run();
    onClose();
  };

  const presetSizes = [
    { label: '小', w: '200' },
    { label: '中', w: '400' },
    { label: '大', w: '600' },
    { label: '全宽', w: '100%' },
    { label: '原始', w: '' },
  ];

  return (
    <div
      className="absolute z-50 rounded-lg border border-slate-200 bg-white p-4 shadow-xl"
      style={{
        minWidth: 320,
        left: `${position.x}px`,
        top: `${position.y - 10}px`,
        transform: 'translate(-50%, -100%)',
      }}
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">图片样式</span>
        <button
          className="text-slate-400 hover:text-slate-600"
          onClick={onClose}
        >
          ✕
        </button>
      </div>

      {/* 预设尺寸 */}
      <div className="mb-3">
        <label className="mb-1 block text-xs text-slate-500">快速尺寸</label>
        <div className="flex gap-1">
          {presetSizes.map((s) => (
            <button
              key={s.label}
              className={`rounded px-2 py-1 text-xs ${
                width === s.w
                  ? 'bg-slate-800 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
              onClick={() => {
                setWidth(s.w);
                if (s.w && s.w !== '100%') {
                  setHeight('');
                }
              }}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* 自定义尺寸 */}
      <div className="mb-3 grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-xs text-slate-500">宽度 (px)</label>
          <input
            type="text"
            value={width}
            onChange={(e) => setWidth(e.target.value)}
            placeholder="auto"
            className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">高度 (px)</label>
          <input
            type="text"
            value={height}
            onChange={(e) => setHeight(e.target.value)}
            placeholder="auto"
            className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
          />
        </div>
      </div>

      {/* 对齐方式 */}
      <div className="mb-3">
        <label className="mb-1 block text-xs text-slate-500">对齐方式</label>
        <div className="flex gap-1">
          {[
            { v: 'none' as const, label: '默认' },
            { v: 'left' as const, label: '左浮动' },
            { v: 'center' as const, label: '居中' },
            { v: 'right' as const, label: '右浮动' },
          ].map((a) => (
            <button
              key={a.v}
              className={`rounded px-2 py-1 text-xs ${
                align === a.v
                  ? 'bg-slate-800 text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
              onClick={() => setAlign(a.v)}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>

      {/* Alt 文本 */}
      <div className="mb-3">
        <label className="mb-1 block text-xs text-slate-500">Alt 文本（SEO / 无障碍）</label>
        <input
          type="text"
          value={alt}
          onChange={(e) => setAlt(e.target.value)}
          placeholder="描述图片内容..."
          className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
        />
      </div>

      {/* 操作按钮 */}
      <div className="flex items-center justify-between">
        <button
          className="rounded px-3 py-1.5 text-xs text-red-500 hover:bg-red-50"
          onClick={deleteImage}
        >
          删除图片
        </button>
        <div className="flex gap-2">
          <button
            className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
            onClick={onClose}
          >
            取消
          </button>
          <button
            className="rounded bg-slate-800 px-3 py-1.5 text-xs text-white hover:bg-slate-700"
            onClick={applyChanges}
          >
            应用
          </button>
        </div>
      </div>
    </div>
  );
}

// ---- 工具栏组件 ----
function EditorToolbar({
  editor,
  onImagePick,
}: {
  editor: Editor | null;
  onImagePick: () => void;
}): JSX.Element | null {
  if (!editor) return null;

  // 链接处理
  const setLink = () => {
    const prev = editor.getAttributes('link').href ?? '';
    const url = window.prompt('输入链接 URL', prev);
    if (url === null) return;
    if (url === '') {
      editor.chain().focus().extendMarkRange('link').unsetLink().run();
      return;
    }
    editor.chain().focus().extendMarkRange('link').setLink({ href: url }).run();
  };

  // 颜色列表
  const colors = [
    { label: '黑', value: '#1e293b' },
    { label: '红', value: '#ef4444' },
    { label: '橙', value: '#f97316' },
    { label: '绿', value: '#22c55e' },
    { label: '蓝', value: '#3b82f6' },
    { label: '紫', value: '#a855f7' },
  ];

  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-slate-200 bg-slate-50 px-3 py-2">
      {/* === 第一组：段落格式 === */}
      <select
        className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700"
        value={
          editor.isActive('heading', { level: 1 }) ? 'h1'
          : editor.isActive('heading', { level: 2 }) ? 'h2'
          : editor.isActive('heading', { level: 3 }) ? 'h3'
          : 'p'
        }
        onChange={(e) => {
          const v = e.target.value;
          if (v === 'p') editor.chain().focus().setParagraph().run();
          else if (v === 'h1') editor.chain().focus().toggleHeading({ level: 1 }).run();
          else if (v === 'h2') editor.chain().focus().toggleHeading({ level: 2 }).run();
          else if (v === 'h3') editor.chain().focus().toggleHeading({ level: 3 }).run();
        }}
      >
        <option value="p">正文</option>
        <option value="h1">标题 1</option>
        <option value="h2">标题 2</option>
        <option value="h3">标题 3</option>
      </select>

      <Sep />

      {/* === 第二组：文字样式 === */}
      <ToolBtn
        active={editor.isActive('bold')}
        onClick={() => editor.chain().focus().toggleBold().run()}
        label={<span className="font-bold">B</span>}
        title="加粗 (Ctrl+B)"
      />
      <ToolBtn
        active={editor.isActive('italic')}
        onClick={() => editor.chain().focus().toggleItalic().run()}
        label={<span className="italic">I</span>}
        title="斜体 (Ctrl+I)"
      />
      <ToolBtn
        active={editor.isActive('underline')}
        onClick={() => editor.chain().focus().toggleUnderline().run()}
        label={<span className="underline">U</span>}
        title="下划线 (Ctrl+U)"
      />
      <ToolBtn
        active={editor.isActive('strike')}
        onClick={() => editor.chain().focus().toggleStrike().run()}
        label={<span className="line-through">S</span>}
        title="删除线"
      />
      <ToolBtn
        active={editor.isActive('code')}
        onClick={() => editor.chain().focus().toggleCode().run()}
        label="< >"
        title="行内代码"
      />
      <ToolBtn
        active={editor.isActive('highlight')}
        onClick={() => editor.chain().focus().toggleHighlight().run()}
        label={<span className="bg-yellow-200 px-0.5 rounded">H</span>}
        title="高亮标记"
      />

      <Sep />

      {/* === 第三组：文字颜色 === */}
      {colors.map((c) => (
        <button
          key={c.value}
          type="button"
          className="h-5 w-5 rounded border border-slate-300 transition-transform hover:scale-110"
          style={{ backgroundColor: c.value }}
          onClick={() => editor.chain().focus().setColor(c.value).run()}
          title={`文字颜色: ${c.label}`}
        />
      ))}
      <button
        type="button"
        className="h-5 w-5 rounded border border-slate-300 bg-white text-[8px] text-slate-400"
        onClick={() => editor.chain().focus().unsetColor().run()}
        title="清除颜色"
      >
        ×
      </button>

      <Sep />

      {/* === 第四组：对齐 === */}
      <ToolBtn
        active={editor.isActive({ textAlign: 'left' })}
        onClick={() => editor.chain().focus().setTextAlign('left').run()}
        label="⫷"
        title="左对齐"
      />
      <ToolBtn
        active={editor.isActive({ textAlign: 'center' })}
        onClick={() => editor.chain().focus().setTextAlign('center').run()}
        label="☰"
        title="居中对齐"
      />
      <ToolBtn
        active={editor.isActive({ textAlign: 'right' })}
        onClick={() => editor.chain().focus().setTextAlign('right').run()}
        label="⫸"
        title="右对齐"
      />

      <Sep />

      {/* === 第五组：列表 === */}
      <ToolBtn
        active={editor.isActive('bulletList')}
        onClick={() => editor.chain().focus().toggleBulletList().run()}
        label="• 列表"
        title="无序列表"
      />
      <ToolBtn
        active={editor.isActive('orderedList')}
        onClick={() => editor.chain().focus().toggleOrderedList().run()}
        label="1. 列表"
        title="有序列表"
      />

      <Sep />

      {/* === 第六组：块级元素 === */}
      <ToolBtn
        active={editor.isActive('blockquote')}
        onClick={() => editor.chain().focus().toggleBlockquote().run()}
        label="❝ 引用"
        title="引用块"
      />
      <ToolBtn
        active={editor.isActive('codeBlock')}
        onClick={() => editor.chain().focus().toggleCodeBlock().run()}
        label="{ } 代码"
        title="代码块"
      />
      <ToolBtn
        active={false}
        onClick={() => editor.chain().focus().setHorizontalRule().run()}
        label="— 分割"
        title="水平分割线"
      />

      <Sep />

      {/* === 第七组：链接 / 图片 === */}
      <ToolBtn
        active={editor.isActive('link')}
        onClick={setLink}
        label="🔗 链接"
        title="插入/编辑链接"
      />
      <ToolBtn
        active={false}
        onClick={onImagePick}
        label="🖼 图片"
        title="从本地选择图片插入"
      />

      <Sep />

      {/* === 第八组：撤销 / 重做 === */}
      <ToolBtn
        active={false}
        onClick={() => editor.chain().focus().undo().run()}
        label="↩"
        title="撤销 (Ctrl+Z)"
      />
      <ToolBtn
        active={false}
        onClick={() => editor.chain().focus().redo().run()}
        label="↪"
        title="重做 (Ctrl+Y)"
      />
    </div>
  );
}

// ---- 主页面 ----

export function ArticleEditorPage(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [article, setArticle] = useState<ArticleDetail | null>(null);
  const [versions, setVersions] = useState<ArticleVersion[]>([]);
  const [msg, setMsg] = useState('');
  const [generating, setGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showImagePanel, setShowImagePanel] = useState(false);
  const [imagePanelPos, setImagePanelPos] = useState({ x: 0, y: 0 });
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [showPublishDialog, setShowPublishDialog] = useState(false);
  const editorContainerRef = useRef<HTMLDivElement>(null);

  // 图片文件选择
  const imageInputRef = useRef<HTMLInputElement>(null);

  // TipTap 编辑器（全部扩展）
  const editor = useEditor({
    extensions: [
      StarterKit,
      Placeholder.configure({ placeholder: '开始写作，或点击上方"AI 生成"按钮...' }),
      Underline,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      Highlight,
      Link.configure({ openOnClick: false }),
      Image.configure({ allowBase64: true, inline: false }),
      TextStyle,
      Color,
    ],
    content: '',
    editorProps: {
      attributes: {
        class: 'prose prose-sm sm:prose max-w-none focus:outline-none min-h-[400px] px-4 py-3',
      },
      handleDOMEvents: {
        // 点击图片时显示样式面板
        click: (_view, event) => {
          const target = event.target as HTMLElement;
          if (target.tagName === 'IMG') {
            const pos = _view.posAtDOM(target, 0);
            if (pos !== undefined) {
              editor?.chain().focus().setNodeSelection(pos).run();
              // 计算图片相对于编辑器容器的位置
              const container = editorContainerRef.current;
              if (container) {
                const containerRect = container.getBoundingClientRect();
                const imgRect = target.getBoundingClientRect();
                setImagePanelPos({
                  x: imgRect.left - containerRect.left + imgRect.width / 2,
                  y: imgRect.top - containerRect.top,
                });
              }
              setShowImagePanel(true);
            }
          } else {
            setShowImagePanel(false);
          }
          return false;
        },
      },
    },
  });

  // 图片文件选择处理
  const handleImagePick = useCallback(() => {
    imageInputRef.current?.click();
  }, []);

  const handleImageFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file || !editor) return;
      if (!file.type.startsWith('image/')) {
        setMsg('请选择图片文件');
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        setMsg('图片不能超过 5MB');
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const src = reader.result as string;
        editor.chain().focus().setImage({ src }).run();
        setMsg('图片已插入，点击图片可编辑样式');
      };
      reader.onerror = () => setMsg('图片读取失败');
      reader.readAsDataURL(file);
      e.target.value = '';
    },
    [editor],
  );

  // 加载文章
  const loadArticle = useCallback(async () => {
    if (!id) return;
    try {
      const art = await getArticle(id);
      setArticle(art);
      if (editor && art.content) {
        // 判断内容是 HTML 还是 Markdown
        // HTML 特征：< 开头的标签 或 包含 base64 图片
        const isHtml = art.content.startsWith('<') || art.content.includes('data:image');
        editor.commands.setContent(isHtml ? art.content : markdownToHtml(art.content));
      }
    } catch (e) {
      setMsg(`加载失败: ${(e as { message?: string }).message ?? e}`);
    }
  }, [id, editor]);

  const loadVersions = useCallback(async () => {
    if (!id) return;
    try {
      const r = await listVersions(id);
      setVersions(r.items);
    } catch { /* 忽略 */ }
  }, [id]);

  // ⚠️ 修复无限循环：effect 只依赖 id/editor（会变的值），不依赖 callback 函数本身
  // callback 已经用 useCallback 固定了依赖，这里再依赖它们会造成循环
  useEffect(() => {
    void loadArticle();
    void loadVersions();
  }, [id, editor]);  // 只依赖真正会变的值

  // 保存（直接保存 HTML，保留图片等富文本格式）
  async function onSave(): Promise<void> {
    if (!id || !editor) return;
    setSaving(true);
    try {
      const content = editor.getHTML();
      await updateArticle(id, { content });
      setMsg('已保存');
    } catch (e) {
      setMsg(`保存失败: ${(e as { message?: string }).message ?? e}`);
    } finally {
      setSaving(false);
    }
  }

  // AI 生成
  async function onGenerate(): Promise<void> {
    if (!id) return;
    if (!confirm('触发 AI 生成将覆盖当前正文，确定？')) return;
    setGenerating(true);
    setMsg('正在生成（四阶段管线，约 30-90 秒）...');
    try {
      const art = await generateArticle(id);
      setArticle(art);
      if (editor && art.content) {
        editor.commands.setContent(markdownToHtml(art.content));
      }
      setMsg(art.status === 'completed' ? '生成完成！' : `生成失败：${art.error_message}`);
      void loadVersions();
    } catch (e) {
      setMsg(`生成失败: ${(e as { message?: string }).message ?? e}`);
    } finally {
      setGenerating(false);
    }
  }

  // 打版本快照
  async function onSaveVersion(): Promise<void> {
    if (!id) return;
    const note = prompt('版本说明（可选）') || '';
    try {
      await saveVersion(id, note || undefined);
      setMsg('版本已保存');
      void loadVersions();
    } catch (e) {
      setMsg(`版本保存失败: ${(e as { message?: string }).message ?? e}`);
    }
  }

  // 回退到某版本
  function onRestore(v: ArticleVersion): void {
    if (!editor) return;
    if (!confirm(`回退到 v${v.version_no}？当前内容将被覆盖。`)) return;
    editor.commands.setContent(markdownToHtml(v.content));
    setMsg(`已回退到 v${v.version_no}，记得保存`);
  }

  if (!article) {
    return (
      <div className="flex min-h-screen items-center justify-center text-slate-400">
        加载中...
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* 顶栏 */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white px-6 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button className="text-sm text-slate-500 hover:text-slate-800" onClick={() => navigate('/articles')}>
              ← 文章列表
            </button>
            <span className="text-sm text-slate-300">|</span>
            <span className="text-sm font-medium text-slate-700">{article.title}</span>
            <StatusDot status={article.status} />
          </div>
          <div className="flex items-center gap-2">
            {msg && <span className="text-xs text-slate-500">{msg}</span>}
            <button
              className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              onClick={() => setShowExportDialog(true)}
            >
              📤 导出
            </button>
            <button
              className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              onClick={() => setShowPublishDialog(true)}
            >
              🚀 发布
            </button>
            <button
              className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
              onClick={() => void onSaveVersion()}
            >
              保存版本
            </button>
            <button
              className="rounded border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50 disabled:opacity-50"
              onClick={() => void onSave()}
              disabled={saving}
            >
              {saving ? '保存中...' : '保存'}
            </button>
            <button
              className="rounded bg-slate-800 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => void onGenerate()}
              disabled={generating}
            >
              {generating ? '生成中...' : '✦ AI 生成'}
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-6 py-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
          {/* 编辑器主区 */}
          <div className="lg:col-span-3">
            {/* 工具栏容器（sticky） */}
            <div className="sticky top-0 z-10 rounded-t-lg border border-slate-200 bg-white shadow-sm">
              {editor && <EditorToolbar editor={editor} onImagePick={handleImagePick} />}
            </div>

            {/* 编辑器内容区 */}
            <div ref={editorContainerRef} className="relative border-x border-b border-slate-200 rounded-b-lg bg-white">
              <div className="article-editor-content px-4 py-3 min-h-[400px] focus-within:outline-none">
                <EditorContent editor={editor} />
              </div>
              {/* 隐藏的文件选择器 */}
              <input
                ref={imageInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleImageFile}
              />
              {/* 图片样式弹出面板 */}
              {showImagePanel && editor && (
                <ImageStylePanel
                  editor={editor}
                  onClose={() => setShowImagePanel(false)}
                  position={imagePanelPos}
                />
              )}
            </div>
          </div>

          {/* 右侧栏：SEO + 版本 */}
          <div className="space-y-4">
            {/* SEO 预览 */}
            {article.seo_meta && (
              <div className="rounded-lg border border-slate-200 bg-white p-4">
                <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">SEO 预览</h3>
                <div className="space-y-1 text-sm">
                  <p className="font-medium text-blue-700">{article.seo_meta.meta_title || article.title}</p>
                  <p className="text-xs text-green-700">{article.seo_meta.meta_description || ''}</p>
                  {article.seo_meta.keywords && article.seo_meta.keywords.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {article.seo_meta.keywords.map((kw) => (
                        <span key={kw} className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                          {kw}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 文章信息 */}
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">文章信息</h3>
              <dl className="space-y-1 text-xs text-slate-600">
                <div className="flex justify-between"><dt>模板</dt><dd>{article.template_code}</dd></div>
                <div className="flex justify-between"><dt>字数</dt><dd>{article.word_count}</dd></div>
                <div className="flex justify-between"><dt>状态</dt><dd>{article.status}</dd></div>
              </dl>
            </div>

            {/* 版本历史 */}
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase text-slate-500">
                版本历史（{versions.length}）
              </h3>
              {versions.length === 0 ? (
                <p className="text-xs text-slate-400">暂无版本</p>
              ) : (
                <ul className="space-y-1">
                  {versions.map((v) => (
                    <li key={v.id} className="flex items-center justify-between text-xs">
                      <span className="text-slate-600">
                        v{v.version_no} {v.note ? `· ${v.note}` : ''}
                      </span>
                      <button
                        className="text-blue-500 hover:underline"
                        onClick={() => onRestore(v)}
                      >
                        回退
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 导出对话框 */}
      {showExportDialog && (
        <ExportDialog
          articleId={id!}
          articleTitle={article?.title || '文章'}
          onClose={() => setShowExportDialog(false)}
        />
      )}

      {/* 发布对话框 */}
      {showPublishDialog && (
        <PublishDialog
          articleId={id!}
          onClose={() => setShowPublishDialog(false)}
          onSuccess={() => setMsg('发布成功')}
        />
      )}
    </div>
  );
}

// ---- 辅助 ----

function StatusDot({ status }: { status: string }): JSX.Element {
  const colors: Record<string, string> = {
    draft: 'bg-slate-400',
    completed: 'bg-green-500',
    published: 'bg-blue-500',
    failed: 'bg-red-500',
  };
  return <span className={`inline-block h-2 w-2 rounded-full ${colors[status] ?? 'bg-slate-400'}`} />;
}

// 简易 Markdown → HTML
function markdownToHtml(md: string): string {
  if (!md) return '';
  return md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/^/, '<p>')
    .replace(/$/, '</p>');
}
