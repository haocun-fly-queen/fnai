// Dashboard page: shows user info + workspace switcher + logout.
//
// 这个页面是用户登录后看到的第一个页面，核心功能：
// 1. 显示当前用户信息
// 2. workspace 切换器（多租户的核心 UX）
// 3. Sign out 按钮
//
// 给 Java 背景同事的提示：
// - React 函数组件 ≈ Java 的"无状态 Controller"（但有 hooks 管理状态）
// - useState/useEffect 是 React 的"声明式生命周期"
// - useNavigate 是 React Router 6 的"声明式跳转"

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { listMyTenants, switchTenant } from '@/lib/tenant-api';

export function DashboardPage(): JSX.Element {
  const navigate = useNavigate();

  // 从 zustand store 解构出需要的字段
  // ⚠️ 注意：这里只读不写。如果要改 store，调用 store 提供的方法
  // （switchActiveTenant, clear 等）
  const { user, activeTenantId, switchActiveTenant, clear } = useAuthStore();

  // 本地状态：远端拉来的"完整租户列表"（带 role 和 is_active）
  // 为什么 store 里的 memberships 不够用？
  //   store 里的 memberships 是登录时存的，role 信息是当时的。
  //   如果用户在另一个客户端被改了角色，store 里的数据是过期的。
  //   所以 dashboard 重新从 /tenants/mine 拉一次最新的。
  const [tenants, setTenants] = useState<
    Array<{
      id: string;
      name: string;
      slug: string;
      role: string;
      is_active: boolean;
    }>
  >([]);

  // 切换中的 loading 状态（防止用户连点切换按钮）
  const [switching, setSwitching] = useState(false);

  // 错误信息（用 alert 太丑，用 inline 显示）
  const [error, setError] = useState<string | null>(null);

  // 组件挂载时拉一次最新租户列表
  useEffect(() => {
    const abortController = new AbortController();

    async function load(): Promise<void> {
      try {
        // TODO: listMyTenants() 暂不支持 AbortSignal，需要在 lib/api.ts 所有方法加 signal 参数
        // 当前 abortController.abort() 只能阻止 setState，实际 HTTP 请求仍在飞
        const data = await listMyTenants();
        if (abortController.signal.aborted) return;

        // 把后端返回的 TenantWithMembership 压成页面要用的形状
        setTenants(
          data.items.map((t) => ({
            id: t.id,
            name: t.name,
            slug: t.slug,
            role: t.role,
            is_active: t.is_active,
          })),
        );
      } catch (err) {
        if (abortController.signal.aborted) return;
        // ⚠️ 401 已经被 axios 拦截器处理（自动跳登录），所以这里
        // 看到的都是非 401 错误（网络错、500 等）
        console.error('Failed to load tenants', err);
      }
    }

    load();
    return () => {
      abortController.abort();
    };
  }, []);

  /**
   * 处理 workspace 切换。
   *
   * 流程：
   * 1. 调 /tenants/switch
   * 2. 成功后用响应里的新 token + active_tenant 更新 store
   * 3. 重新拉一次 tenants 列表（is_active 标记会变化）
   */
  async function onSwitchTenant(tenantId: string): Promise<void> {
    if (switching || tenantId === activeTenantId) return;
    setError(null);
    setSwitching(true);
    try {
      const result = await switchTenant(tenantId);

      // 关键：更新 store 里的 token + activeTenantId
      switchActiveTenant({
        accessToken: result.access_token,
        refreshToken: result.refresh_token,
        activeTenantId: result.active_tenant.id,
      });

      // 重新拉一次列表，让 is_active 标记正确
      const data = await listMyTenants();
      setTenants(
        data.items.map((t) => ({
          id: t.id,
          name: t.name,
          slug: t.slug,
          role: t.role,
          is_active: t.is_active,
        })),
      );
    } catch (err) {
      // ⚠️ axios 拦截器已经把 ApiError 标准化成 Error 对象
      // err.message 就是后端返回的 message 字段
      const message = err instanceof Error ? err.message : '切换失败';
      setError(message);
    } finally {
      setSwitching(false);
    }
  }

  function onLogout(): void {
    clear();
    navigate('/login');
  }

  // 当前激活的租户对象（用于顶部展示）
  const currentTenant = tenants.find((t) => t.id === activeTenantId);

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ---------- 顶部导航 ---------- */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <h1 className="text-lg font-semibold text-slate-900">FNAI</h1>
          <div className="flex items-center gap-3">
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

      <main className="mx-auto max-w-3xl space-y-6 px-6 py-10">
        {/* ---------- 开发测试入口（生产前删除） ---------- */}
        <section className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div>
            <div className="text-sm font-medium text-amber-900">开发测试</div>
            <div className="mt-0.5 text-xs text-amber-700">
              测后端 4 个权限端点（OWNER/ADMIN/MEMBER/Any）
            </div>
          </div>
          <button
            onClick={() => navigate('/test-panel')}
            className="rounded-md bg-amber-900 px-3 py-1.5 text-sm text-white hover:bg-amber-800"
          >
            打开 Test Panel →
          </button>
        </section>

        {/* ---------- 欢迎区 ---------- */}
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <h2 className="mb-1 text-base font-semibold text-slate-900">欢迎回来</h2>
          <p className="text-sm text-slate-600">
            你好 {user?.full_name || user?.email}，你已登录。
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={() => navigate('/team')}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
            >
              团队管理 →
            </button>
            <button
              onClick={() => navigate('/knowledge')}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
            >
              知识库 →
            </button>
            <button
              onClick={() => navigate('/articles')}
              className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800"
            >
              文章管理 →
            </button>
            <button
              onClick={() => navigate('/test-panel')}
              className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
            >
              权限测试
            </button>
          </div>
        </section>

        {/* ---------- Workspace 切换器 ---------- */}
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-900">我的工作空间</h2>
            {currentTenant && (
              <span className="text-xs text-slate-500">
                当前激活：<span className="font-medium text-slate-700">{currentTenant.name}</span>
              </span>
            )}
          </div>

          {/* 错误信息条 */}
          {error && (
            <div className="mb-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {tenants.length === 0 ? (
            <p className="text-sm text-slate-500">你还没有加入任何工作空间。</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {tenants.map((t) => {
                // 是否是当前激活的租户
                const isActive = t.id === activeTenantId;
                return (
                  <li
                    key={t.id}
                    className="-mx-2 flex items-center justify-between rounded px-2 py-3 hover:bg-slate-50"
                  >
                    <button
                      onClick={() => onSwitchTenant(t.id)}
                      disabled={switching || isActive}
                      className="flex-1 text-left disabled:cursor-not-allowed"
                    >
                      <div className="flex items-center gap-2">
                        <div className="text-sm font-medium text-slate-900">{t.name}</div>
                        {isActive && (
                          <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] tracking-wide text-emerald-700">
                            当前
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-500">/{t.slug}</div>
                    </button>
                    <span className="rounded bg-slate-100 px-2 py-1 text-xs text-slate-700">
                      {t.role}
                    </span>
                  </li>
                );
              })}
            </ul>
          )}

          {switching && <p className="mt-3 text-xs text-slate-500">切换工作空间中…</p>}
        </section>
      </main>
    </div>
  );
}
