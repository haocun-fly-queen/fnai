import { useEffect, useState, type JSX } from 'react';

interface HealthResponse {
  status: string;
}

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1';

export function App(): JSX.Element {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then((res) => res.json())
      .then((data: HealthResponse) => setHealth(data))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : 'unknown'));
  }, []);

  return (
    <div className="min-h-screen px-4 py-12 sm:px-6 lg:px-8">
      <main className="mx-auto max-w-3xl animate-fade-in">
        <header className="mb-8">
          <h1 className="bg-gradient-to-r from-primary-600 to-primary-400 bg-clip-text text-4xl font-bold tracking-tight text-transparent">
            FNAI
          </h1>
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
            AI 内容生产平台 · V1 阶段 1 启动版
          </p>
        </header>

        <section className="card animate-slide-up">
          <h2 className="text-lg font-semibold">环境检查</h2>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-gray-600 dark:text-gray-400">后端连通</span>
              {error ? (
                <span className="font-mono text-red-500">❌ {error}</span>
              ) : health ? (
                <span className="font-mono text-green-500">✅ {health.status}</span>
              ) : (
                <span className="text-gray-400">检测中…</span>
              )}
            </div>
          </div>
        </section>

        <section className="card mt-6 animate-slide-up">
          <h2 className="text-lg font-semibold">即将到来</h2>
          <ul className="mt-4 space-y-2 text-sm text-gray-700 dark:text-gray-300">
            <li>📝 W3-W4：注册登录 + 多租户</li>
            <li>📚 W5-W7：知识库 + RAG 检索</li>
            <li>✍️ W8-W11：文章生成核心</li>
            <li>🚀 W12-W13：WordPress 发布</li>
            <li>🧪 W14-W16：联调 + 灰度内测</li>
          </ul>
        </section>
      </main>
    </div>
  );
}
