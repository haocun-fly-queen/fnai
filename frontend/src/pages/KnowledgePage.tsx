// 知识库页面（Step 5）—— 简单版：KB 列表/创建 + 文档上传/列表 + 检索测试。
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  listKbs,
  createKb,
  listDocuments,
  uploadDocument,
  searchKb,
  type KnowledgeBase,
  type DocumentItem,
  type SearchResultItem,
} from '@/lib/knowledge-api';

export function KnowledgePage(): JSX.Element {
  const navigate = useNavigate();
  const [kbs, setKbs] = useState<KnowledgeBase[]>([]);
  const [activeKb, setActiveKb] = useState<KnowledgeBase | null>(null);
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [msg, setMsg] = useState<string>('');

  // 新建 KB 表单
  const [newName, setNewName] = useState('');
  const [newSlug, setNewSlug] = useState('');

  // 检索
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResultItem[]>([]);

  async function refreshKbs(): Promise<void> {
    try {
      const r = await listKbs();
      setKbs(r.items);
    } catch (e) {
      setMsg(`加载知识库失败: ${(e as { message?: string }).message ?? e}`);
    }
  }

  async function refreshDocs(kbId: string): Promise<void> {
    const r = await listDocuments(kbId);
    setDocs(r.items);
  }

  useEffect(() => {
    void refreshKbs();
  }, []);

  async function onCreateKb(): Promise<void> {
    if (!newName || !newSlug) {
      setMsg('请填名字和 slug');
      return;
    }
    try {
      await createKb(newName, newSlug);
      setNewName('');
      setNewSlug('');
      setMsg('知识库已创建');
      await refreshKbs();
    } catch (e) {
      setMsg(`创建失败: ${(e as { message?: string }).message ?? e}`);
    }
  }

  async function onSelectKb(kb: KnowledgeBase): Promise<void> {
    setActiveKb(kb);
    setResults([]);
    await refreshDocs(kb.id);
  }

  async function onUpload(file: File | undefined): Promise<void> {
    if (!file || !activeKb) return;
    try {
      setMsg('上传中...');
      await uploadDocument(activeKb.id, file);
      setMsg('上传成功，正在后台处理（解析+向量化），稍后刷新看状态');
      await refreshDocs(activeKb.id);
    } catch (e) {
      setMsg(`上传失败: ${(e as { message?: string }).message ?? e}`);
    }
  }

  async function onSearch(): Promise<void> {
    if (!query || !activeKb) return;
    try {
      const r = await searchKb(activeKb.id, query);
      setResults(r.items);
      setMsg(`检索到 ${r.total} 条`);
    } catch (e) {
      setMsg(`检索失败: ${(e as { message?: string }).message ?? e}`);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <header className="mb-6 flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-800">知识库</h1>
        <button
          className="text-sm text-slate-500 hover:text-slate-800"
          onClick={() => navigate('/dashboard')}
        >
          返回工作台
        </button>
      </header>

      {msg && (
        <div className="mb-4 rounded border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">
          {msg}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 左：KB 列表 + 新建 */}
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-medium text-slate-700">知识库列表</h2>
          <ul className="mb-4 space-y-1">
            {kbs.map((kb) => (
              <li key={kb.id}>
                <button
                  className={`w-full rounded px-3 py-2 text-left text-sm ${
                    activeKb?.id === kb.id ? 'bg-slate-800 text-white' : 'hover:bg-slate-100'
                  }`}
                  onClick={() => void onSelectKb(kb)}
                >
                  {kb.name} <span className="opacity-60">({kb.document_count} 文档)</span>
                </button>
              </li>
            ))}
            {kbs.length === 0 && <li className="text-sm text-slate-400">还没有知识库</li>}
          </ul>
          <div className="space-y-2 border-t border-slate-100 pt-3">
            <input
              className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
              placeholder="名字"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <input
              className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
              placeholder="slug（小写字母/数字/连字符）"
              value={newSlug}
              onChange={(e) => setNewSlug(e.target.value)}
            />
            <button
              className="w-full rounded bg-slate-800 py-1.5 text-sm text-white hover:bg-slate-700"
              onClick={() => void onCreateKb()}
            >
              新建知识库
            </button>
          </div>
        </section>

        {/* 中：文档列表 + 上传 */}
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-medium text-slate-700">
            文档{activeKb ? `（${activeKb.name}）` : ''}
          </h2>
          {!activeKb && <p className="text-sm text-slate-400">先在左侧选一个知识库</p>}
          {activeKb && (
            <>
              <div className="mb-3 flex items-center gap-2">
                <input
                  type="file"
                  className="text-sm"
                  onChange={(e) => void onUpload(e.target.files?.[0])}
                />
                <button
                  className="rounded border border-slate-300 px-2 py-1 text-xs hover:bg-slate-100"
                  onClick={() => void refreshDocs(activeKb.id)}
                >
                  刷新
                </button>
              </div>
              <ul className="space-y-1">
                {docs.map((d) => (
                  <li key={d.id} className="rounded bg-slate-50 px-2 py-1.5 text-sm">
                    <div className="flex justify-between">
                      <span className="truncate">{d.filename}</span>
                      <StatusBadge status={d.status} />
                    </div>
                    {d.status === 'ready' && (
                      <span className="text-xs text-slate-400">{d.chunk_count} 个分片</span>
                    )}
                    {d.status === 'failed' && d.error_message && (
                      <span className="text-xs text-red-500">{d.error_message}</span>
                    )}
                  </li>
                ))}
                {docs.length === 0 && <li className="text-sm text-slate-400">还没有文档</li>}
              </ul>
            </>
          )}
        </section>

        {/* 右：检索测试 */}
        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="mb-3 font-medium text-slate-700">语义检索</h2>
          {!activeKb && <p className="text-sm text-slate-400">先选一个知识库</p>}
          {activeKb && (
            <>
              <div className="mb-3 flex gap-2">
                <input
                  className="flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
                  placeholder="输入要检索的问题"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && void onSearch()}
                />
                <button
                  className="rounded bg-slate-800 px-3 py-1 text-sm text-white hover:bg-slate-700"
                  onClick={() => void onSearch()}
                >
                  检索
                </button>
              </div>
              <ul className="space-y-2">
                {results.map((r) => (
                  <li key={r.chunk_id} className="rounded bg-slate-50 px-2 py-2 text-sm">
                    <div className="mb-1 flex justify-between text-xs text-slate-400">
                      <span>{r.filename}</span>
                      <span>相似度 {r.score.toFixed(3)}</span>
                    </div>
                    <p className="text-slate-700">{r.content}</p>
                  </li>
                ))}
                {results.length === 0 && (
                  <li className="text-sm text-slate-400">暂无结果</li>
                )}
              </ul>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

// 文档状态小标签
function StatusBadge({ status }: { status: string }): JSX.Element {
  const map: Record<string, string> = {
    pending: 'bg-slate-200 text-slate-600',
    processing: 'bg-yellow-100 text-yellow-700',
    ready: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
  };
  const label: Record<string, string> = {
    pending: '待处理',
    processing: '处理中',
    ready: '就绪',
    failed: '失败',
  };
  return (
    <span className={`ml-2 rounded px-1.5 py-0.5 text-xs ${map[status] ?? 'bg-slate-200'}`}>
      {label[status] ?? status}
    </span>
  );
}
