// Test Panel —— 后端权限端点的可视化测试页面。
//
// 这个页面是"开发测试桩"，生产前会删掉。
// 作用：让团队 7 个人（大多是 Java 背景）能直接在浏览器里验证
//      OWNER/ADMIN/MEMBER/VIEWER 的权限差异，不用切到 curl。
//
// 给 Java 同事的提示：
// - 这相当于 Spring Security 的 @WithMockUser 注解的浏览器版
// - 点按钮 = 调后端 + 显示 200/403/401 结果
// - 顶部卡片显示"我是谁"（token 解码后的 sub/active_tenant_id）

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { callDemo, decodeJwtPayload, type DemoResult } from '@/lib/demo-api';

// 4 个测试端点定义（和后端 demo.py 对应）
const ENDPOINTS = [
  {
    path: '/demo/owner-only',
    method: 'POST' as const,
    label: '仅 OWNER',
    minRole: 'OWNER',
    desc: '只有 OWNER 才能调用',
  },
  {
    path: '/demo/admin-action',
    method: 'POST' as const,
    label: 'ADMIN 及以上',
    minRole: 'ADMIN',
    desc: 'OWNER / ADMIN 可以调用',
  },
  {
    path: '/demo/member-action',
    method: 'POST' as const,
    label: 'MEMBER 及以上',
    minRole: 'MEMBER',
    desc: 'OWNER / ADMIN / MEMBER 可以调用，VIEWER 不行',
  },
  {
    path: '/demo/view-settings',
    method: 'GET' as const,
    label: '任何成员',
    minRole: 'VIEWER',
    desc: '任何成员都能查看',
  },
];

export function TestPanelPage(): JSX.Element {
  const navigate = useNavigate();
  const { accessToken, user, activeTenantId, clear } = useAuthStore();
  const [results, setResults] = useState<Record<string, DemoResult | undefined>>({});
  const [running, setRunning] = useState<string | null>(null);

  // 解码当前 token 的 payload（不验签，只看内容）
  const payload = accessToken ? decodeJwtPayload(accessToken) : null;

  async function runTest(path: string, method: 'GET' | 'POST'): Promise<void> {
    if (!accessToken) return;
    setRunning(path);
    const result = await callDemo(path, method);
    setResults((prev) => ({ ...prev, [path]: result }));
    setRunning(null);
  }

  function copyToken(): void {
    if (accessToken) {
      void navigator.clipboard.writeText(accessToken);
    }
  }

  function onLogout(): void {
    clear();
    navigate('/login');
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ---------- 顶部 ---------- */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold text-slate-900">FNAI</h1>
            <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
              开发测试面板
            </span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => navigate('/dashboard')}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            >
              ← 返回工作台
            </button>
            <span className="text-sm text-slate-600">{user?.email}</span>
            <button
              onClick={onLogout}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            >
              退出登录
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-6 px-6 py-8">
        {/* ---------- 当前身份卡片 ---------- */}
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-3 text-base font-semibold text-slate-900">当前身份</h2>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <div>
              <div className="text-slate-500">邮箱</div>
              <div className="font-mono text-slate-900">{user?.email}</div>
            </div>
            <div>
              <div className="text-slate-500">用户 ID (sub)</div>
              <div className="font-mono text-xs text-slate-900">{String(payload?.sub ?? '—')}</div>
            </div>
            <div>
              <div className="text-slate-500">当前工作空间</div>
              <div className="font-mono text-xs text-slate-900">{activeTenantId ?? '—'}</div>
            </div>
            <div>
              <div className="text-slate-500">Token 过期时间</div>
              <div className="font-mono text-xs text-slate-900">
                {payload?.exp ? new Date(Number(payload.exp) * 1000).toLocaleString() : '—'}
              </div>
            </div>
          </div>
          {accessToken && (
            <div className="mt-3 flex items-center gap-2">
              <code className="flex-1 truncate rounded border border-slate-200 bg-slate-50 px-2 py-1 font-mono text-[10px]">
                {accessToken}
              </code>
              <button
                onClick={copyToken}
                className="rounded bg-slate-200 px-2 py-1 text-xs hover:bg-slate-300"
              >
                复制
              </button>
            </div>
          )}
        </section>

        {/* ---------- 使用说明 ---------- */}
        <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <p>
            <strong>怎么测权限？</strong>
          </p>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-xs">
            <li>用 sushu2@example.com（OWNER）登录 → 4 个按钮都应该是绿色 200</li>
            <li>
              用 viewer@example.com（VIEWER）登录 → 只有"任何成员"是绿色，其他 3 个显示红色 403
            </li>
            <li>想换账号？点右上"退出登录"，再用另一个账号登录</li>
          </ol>
        </section>

        {/* ---------- 4 个测试端点 ---------- */}
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-3 text-base font-semibold text-slate-900">权限端点测试</h2>
          <div className="space-y-3">
            {ENDPOINTS.map((ep) => {
              const result = results[ep.path];
              const isRunning = running === ep.path;
              return (
                <div key={ep.path} className="rounded-md border border-slate-200 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs">
                          {ep.method}
                        </span>
                        <span className="font-mono text-sm text-slate-900">{ep.path}</span>
                        <span className="rounded bg-blue-100 px-1.5 py-0.5 text-xs text-blue-800">
                          最低 {ep.minRole}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">{ep.desc}</p>
                    </div>
                    <button
                      onClick={() => runTest(ep.path, ep.method)}
                      disabled={isRunning}
                      className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
                    >
                      {isRunning ? '调用中…' : '测试'}
                    </button>
                  </div>

                  {/* 结果展示 */}
                  {result && (
                    <div
                      className={`mt-3 rounded-md p-3 font-mono text-sm ${
                        result.ok
                          ? 'border border-emerald-200 bg-emerald-50'
                          : 'border border-red-200 bg-red-50'
                      }`}
                    >
                      <div className={result.ok ? 'text-emerald-800' : 'text-red-800'}>
                        <span className="font-bold">HTTP {result.status}</span>
                        {result.ok ? ' ✅' : ' ❌'}
                      </div>
                      <pre
                        className={`mt-2 whitespace-pre-wrap break-all text-xs ${
                          result.ok ? 'text-emerald-900' : 'text-red-900'
                        }`}
                      >
                        {JSON.stringify(result.body, null, 2)}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      </main>
    </div>
  );
}
