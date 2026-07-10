// 文章列表页 —— 文章管理 + 创建 + 批量生成。
import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listArticles,
  createArticle,
  deleteArticle,
  listTemplates,
  batchGenerate,
  type ArticleSummary,
  type TemplateSummary,
  type BatchGenerateItem,
} from '@/lib/article-api';
import { listKbs, listDocuments, type KnowledgeBase, type DocumentItem } from '@/lib/knowledge-api';
import { api } from '@/lib/api';

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

  // 批量模式
  const [batchMode, setBatchMode] = useState(false);
  const [batchItems, setBatchItems] = useState<BatchGenerateItem[]>([
    { title: '', topic: '' },
  ]);
  const [batchTplCode, setBatchTplCode] = useState('blog');
  const [batchKbId, setBatchKbId] = useState('');
  const [batchDocIds, setBatchDocIds] = useState<string[]>([]);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [batchSubmitting, setBatchSubmitting] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{
    articleIds: string[];
    statuses: Record<string, string>;
  } | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  // 加载 KB 下的文档列表（文件多选用）
  const loadDocs = useCallback(async (kb: string) => {
    if (!kb) {
      setDocs([]);
      return;
    }
    try {
      const res = await listDocuments(kb);
      setDocs(res.items);
    } catch {
      setDocs([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, []);

  // 切换 KB 时加载文档列表
  useEffect(() => {
    void loadDocs(batchMode ? batchKbId : kbId);
  }, [batchMode, batchKbId, kbId, loadDocs]);

  // 轮询批量生成进度
  useEffect(() => {
    if (!batchProgress) {
      if (pollRef.current) clearInterval(pollRef.current);
      return;
    }
    pollRef.current = setInterval(async () => {
      try {
        const results: Record<string, string> = {};
        for (const id of batchProgress.articleIds) {
          try {
            const r = await api.get(`/articles/${id}`);
            results[id] = r.data.status;
          } catch {
            results[id] = 'unknown';
          }
        }
        setBatchProgress((prev) =>
          prev ? { ...prev, statuses: { ...prev.statuses, ...results } } : null,
        );
        // 全部完成则停止轮询
        const allDone = batchProgress.articleIds.every(
          (id) => results[id] === 'completed' || results[id] === 'failed',
        );
        if (allDone) {
          if (pollRef.current) clearInterval(pollRef.current);
          setMsg('✅ 批量生成全部完成');
          void refresh();
        }
      } catch {
        // ignore poll errors
      }
    }, 5000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [batchProgress]);

  // 单篇创建
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

  // 批量提交
  async function onBatchSubmit(): Promise<void> {
    const valid = batchItems.filter((it) => it.title && it.topic);
    if (valid.length === 0) {
      setMsg('请至少填一篇文章的标题和主题');
      return;
    }
    setBatchSubmitting(true);
    try {
      const items: BatchGenerateItem[] = valid.map((it) => ({
        ...it,
        template_code: batchTplCode,
        knowledge_base_id: batchKbId || undefined,
        source_document_ids: batchDocIds.length > 0 ? batchDocIds : undefined,
      }));
      const res = await batchGenerate(items);
      setMsg(`已提交 ${res.article_ids.length} 篇生成任务，正在轮询进度...`);
      setBatchProgress({
        articleIds: res.article_ids,
        statuses: Object.fromEntries(res.article_ids.map((id) => [id, 'draft'])),
      });
    } catch (e) {
      setMsg(`批量提交失败: ${(e as { message?: string }).message ?? e}`);
    } finally {
      setBatchSubmitting(false);
    }
  }

  function updateBatchItem(idx: number, field: 'title' | 'topic', val: string): void {
    setBatchItems((prev) => prev.map((it, i) => (i === idx ? { ...it, [field]: val } : it)));
  }

  function addBatchItem(): void {
    if (batchItems.length >= 20) return;
    setBatchItems((prev) => [...prev, { title: '', topic: '' }]);
  }

  function removeBatchItem(idx: number): void {
    if (batchItems.length <= 1) return;
    setBatchItems((prev) => prev.filter((_, i) => i !== idx));
  }

  function toggleDoc(docId: string): void {
    setBatchDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId],
    );
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

      {/* 模式切换 */}
      <div className="mb-4 flex gap-2">
        <button
          className={`rounded px-3 py-1.5 text-sm font-medium ${!batchMode ? 'bg-slate-800 text-white' : 'border border-slate-300 text-slate-600 hover:bg-white'}`}
          onClick={() => setBatchMode(false)}
        >
          单篇创建
        </button>
        <button
          className={`rounded px-3 py-1.5 text-sm font-medium ${batchMode ? 'bg-slate-800 text-white' : 'border border-slate-300 text-slate-600 hover:bg-white'}`}
          onClick={() => setBatchMode(true)}
        >
          批量生成
        </button>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 左：创建/批量 */}
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          {!batchMode ? (
            /* ---- 单篇创建 ---- */
            <>
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
                  <label className="mb-1 block text-xs text-slate-500">知识库（可选）</label>
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
            </>
          ) : (
            /* ---- 批量生成 ---- */
            <>
              <h2 className="mb-3 font-medium text-slate-700">批量生成</h2>
              <div className="space-y-3">
                <div>
                  <label className="mb-1 block text-xs text-slate-500">模板（全局）</label>
                  <select
                    className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                    value={batchTplCode}
                    onChange={(e) => setBatchTplCode(e.target.value)}
                  >
                    {templates.map((t) => (
                      <option key={t.code} value={t.code}>
                        {t.name}（{t.default_word_count} 字）
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs text-slate-500">知识库（全局，可选）</label>
                  <select
                    className="w-full rounded border border-slate-300 px-2 py-1.5 text-sm"
                    value={batchKbId}
                    onChange={(e) => {
                      setBatchKbId(e.target.value);
                      setBatchDocIds([]);
                    }}
                  >
                    <option value="">不使用知识库</option>
                    {kbs.map((kb) => (
                      <option key={kb.id} value={kb.id}>
                        {kb.name}（{kb.document_count} 文档）
                      </option>
                    ))}
                  </select>
                </div>

                {/* 文件多选 */}
                {batchKbId && docs.length > 0 && (
                  <div>
                    <label className="mb-1 block text-xs text-slate-500">
                      指定文件（可选，不选则检索全部）
                    </label>
                    <div className="max-h-32 space-y-1 overflow-y-auto rounded border border-slate-200 p-2">
                      {docs
                        .filter((d) => d.status === 'ready')
                        .map((d) => (
                          <label key={d.id} className="flex items-center gap-2 text-xs">
                            <input
                              type="checkbox"
                              checked={batchDocIds.includes(d.id)}
                              onChange={() => toggleDoc(d.id)}
                            />
                            <span className="truncate">{d.filename}</span>
                            <span className="text-slate-400">({d.chunk_count} chunks)</span>
                          </label>
                        ))}
                    </div>
                    {batchDocIds.length > 0 && (
                      <p className="mt-1 text-xs text-blue-600">已选 {batchDocIds.length} 个文件</p>
                    )}
                  </div>
                )}

                {/* 文章列表 */}
                <div>
                  <div className="mb-1 flex items-center justify-between">
                    <label className="text-xs text-slate-500">文章列表（{batchItems.length}/20）</label>
                    <button
                      className="text-xs text-blue-600 hover:underline disabled:opacity-50"
                      onClick={addBatchItem}
                      disabled={batchItems.length >= 20}
                    >
                      + 添加一篇
                    </button>
                  </div>
                  <div className="max-h-64 space-y-2 overflow-y-auto">
                    {batchItems.map((it, idx) => (
                      <div key={idx} className="rounded border border-slate-200 p-2">
                        <div className="mb-1 flex items-center justify-between">
                          <span className="text-xs font-medium text-slate-500">#{idx + 1}</span>
                          {batchItems.length > 1 && (
                            <button
                              className="text-xs text-red-400 hover:text-red-600"
                              onClick={() => removeBatchItem(idx)}
                            >
                              ✕
                            </button>
                          )}
                        </div>
                        <input
                          className="mb-1 w-full rounded border border-slate-300 px-2 py-1 text-xs"
                          placeholder="标题"
                          value={it.title}
                          onChange={(e) => updateBatchItem(idx, 'title', e.target.value)}
                        />
                        <textarea
                          className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
                          rows={2}
                          placeholder="主题"
                          value={it.topic}
                          onChange={(e) => updateBatchItem(idx, 'topic', e.target.value)}
                        />
                      </div>
                    ))}
                  </div>
                </div>

                <button
                  className="w-full rounded bg-slate-800 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
                  onClick={() => void onBatchSubmit()}
                  disabled={batchSubmitting}
                >
                  {batchSubmitting ? '提交中...' : `提交 ${batchItems.filter((it) => it.title && it.topic).length} 篇生成`}
                </button>
              </div>
            </>
          )}
        </section>

        {/* 右：文章列表 + 批量进度 */}
        <section className="lg:col-span-2 rounded-lg border border-slate-200 bg-white p-4">
          {/* 批量进度条 */}
          {batchProgress && (
            <div className="mb-4 rounded border border-blue-200 bg-blue-50 p-3">
              <h3 className="mb-2 text-sm font-medium text-blue-800">批量生成进度</h3>
              <div className="space-y-1">
                {batchProgress.articleIds.map((id) => {
                  const st = batchProgress.statuses[id] || 'draft';
                  const pct =
                    st === 'completed' ? 100 : st === 'failed' ? 100 : st === 'generating' ? 50 : 10;
                  const color =
                    st === 'completed'
                      ? 'bg-green-500'
                      : st === 'failed'
                        ? 'bg-red-500'
                        : 'bg-blue-500';
                  return (
                    <div key={id} className="flex items-center gap-2">
                      <span className="w-16 text-xs text-slate-500">{st}</span>
                      <div className="h-2 flex-1 rounded bg-slate-200">
                        <div
                          className={`h-2 rounded ${color} transition-all duration-500`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <button
                        className="text-xs text-blue-600 hover:underline"
                        onClick={() => navigate(`/articles/${id}`)}
                      >
                        查看
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

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
