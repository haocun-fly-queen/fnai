// 文章列表页（阶段 4 Step 5.2）—— 文章管理 + 创建。
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listArticles,
  createArticle,
  deleteArticle,
  listTemplates,
  type ArticleSummary,
  type TemplateSummary,
} from '@/lib/article-api';
import { listKbs, type KnowledgeBase } from '@/lib/knowledge-api';

export function ArticlesPage(): JSX.Element {
  const navigate = useNavigate();
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [msg, setMsg] = useState('');

  // 创建表单
  const [title, setTitle] = useState('');
  const [topic, setTopic] = useState('');
  const [tplCode, setTplCode] = useState('blog');
  const [kbId, setKbId] = useState('');
  const [creating, setCreating] = useState(false);

  async function refresh(): Promise<void> {
    try {
      const [artRes, tplRes, kbRes] = await Promise.all([
        listArticles(),
        listTemplates(),
        listKbs(),
      ]);
      setArticles(artRes.items);
      setTemplates(tplRes.items);
      setKbs(kbRes.items);
    } catch (e) {
      setMsg(`加载失败: ${(e as { message?: string }).message ?? e}`);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function onCreate(): Promise<void> {
    if (!title || !topic) {
      setMsg('请填标题和主题');
      return;
    }
    setCreating(true);
    try {
      const art = await createArticle({
        title,
        topic,
        template_code: tplCode,
        knowledge_base_id: kbId || undefined,
      });
      setTitle('');
      setTopic('');
      setMsg('文章已创建，正在跳转编辑器...');
      navigate(`/articles/${art.id}`);
    } catch (e) {
      setMsg(`创建失败: ${(e as { message?: string }).message ?? e}`);
    } finally {
      setCreating(false);
    }
  }

  async function onDelete(id: string): Promise<void> {
    if (!confirm('确定删除这篇文章？')) return;
    try {
      await deleteArticle(id);
      await refresh();
    } catch (e) {
      setMsg(`删除失败: ${(e as { message?: string }).message ?? e}`);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">文章管理</h1>
        <div className="flex items-center gap-3">
          <button
            className="rounded border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:bg-white"
            onClick={() => navigate('/publish-targets')}
          >
            ⚙️ 发布目标管理
          </button>
          <button className="text-sm text-slate-500 hover:text-slate-800" onClick={() => navigate('/dashboard')}>
            返回工作台
          </button>
        </div>
      </header>

      {msg && (
        <div className="mb-4 rounded border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
          {msg}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 左：创建文章 */}
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-medium text-slate-700">创建新文章</h2>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-xs text-slate-500">标题</label>
              <input
                className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                placeholder="文章标题"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">主题（AI 生成的核心输入）</label>
              <textarea
                className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                rows={3}
                placeholder="例：如何选择适合中小企业的 CRM 系统"
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">模板</label>
              <select
                className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                value={tplCode}
                onChange={(e) => setTplCode(e.target.value)}
              >
                {templates.map((t) => (
                  <option key={t.code} value={t.code}>
                    {t.name}（{t.default_word_count} 字）
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">知识库（可选，给 AI 提供参考资料）</label>
              <select
                className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                value={kbId}
                onChange={(e) => setKbId(e.target.value)}
              >
                <option value="">不使用知识库</option>
                {kbs.map((kb) => (
                  <option key={kb.id} value={kb.id}>
                    {kb.name}（{kb.document_count} 文档）
                  </option>
                ))}
              </select>
            </div>
            <button
              className="w-full rounded bg-slate-800 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
              onClick={() => void onCreate()}
              disabled={creating}
            >
              {creating ? '创建中...' : '创建并编辑'}
            </button>
          </div>
        </section>

        {/* 右：文章列表 */}
        <section className="lg:col-span-2 rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-medium text-slate-700">文章列表（{articles.length}）</h2>
          {articles.length === 0 ? (
            <p className="text-sm text-slate-400">还没有文章，在左侧创建第一篇吧</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {articles.map((a) => (
                <li key={a.id} className="flex items-center justify-between py-3">
                  <div className="min-w-0 flex-1">
                    <button
                      className="block truncate text-left text-sm font-medium text-slate-800 hover:text-slate-600"
                      onClick={() => navigate(`/articles/${a.id}`)}
                    >
                      {a.title || '(无标题)'}
                    </button>
                    <div className="mt-0.5 flex items-center gap-2 text-xs text-slate-400">
                      <span>{a.template_code}</span>
                      <span>·</span>
                      <span>{a.word_count} 字</span>
                      <span>·</span>
                      <span>{new Date(a.updated_at).toLocaleDateString('zh-CN')}</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={a.status} />
                    <button
                      className="rounded px-2 py-1 text-xs text-red-500 hover:bg-red-50"
                      onClick={() => void onDelete(a.id)}
                    >
                      删除
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }): JSX.Element {
  const map: Record<string, { bg: string; text: string; label: string }> = {
    draft: { bg: 'bg-slate-100', text: 'text-slate-600', label: '草稿' },
    completed: { bg: 'bg-green-100', text: 'text-green-700', label: '已完成' },
    published: { bg: 'bg-blue-100', text: 'text-blue-700', label: '已发布' },
    failed: { bg: 'bg-red-100', text: 'text-red-700', label: '失败' },
  };
  const s = map[status] ?? { bg: 'bg-slate-100', text: 'text-slate-600', label: status };
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs ${s.bg} ${s.text}`}>
      {s.label}
    </span>
  );
}
