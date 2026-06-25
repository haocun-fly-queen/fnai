// AcceptInvitationPage —— 处理"用户点邀请链接"的页面。
//
// 业务流程：
// 1. 用户收到邮件 / IM 里的链接：/invitations/accept?token=xxx
// 2. 点进来 → ProtectedRoute 检查登录状态
//    - 没登录 → 跳 /login（让用户先登录或注册）
//    - 已登录 → 展示"接受邀请"页面
// 3. 调 /invitations/accept
// 4. 成功 → 自动切到新工作空间 → 跳 /dashboard
// 5. 失败 → 显示具体错误（已过期/邮箱不一致/已使用）
//
// 给 Java 背景同事的提示：
// - 这相当于 Spring 的 @GetMapping("/invitations/accept") + @RequestParam("token")
// - useSearchParams 拿 URL 查询参数 ≈ @RequestParam
// - useEffect 副作用 ≈ @PostConstruct

import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { acceptInvitation } from '@/lib/invitation-api';
import { listMyTenants, switchTenant } from '@/lib/tenant-api';
import type { AcceptInvitationResponse, ApiError } from '@/types/api';

type PageState =
  | { kind: 'loading' }
  | { kind: 'ready'; token: string }
  | { kind: 'missing_token' }
  | { kind: 'success'; data: AcceptInvitationResponse }
  | { kind: 'error'; code: string; message: string };

export function AcceptInvitationPage(): JSX.Element {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user, switchActiveTenant, clear } = useAuthStore();

  // 状态机：一个变量表示当前在哪个阶段
  const [state, setState] = useState<PageState>({ kind: 'loading' });
  const [accepting, setAccepting] = useState(false);

  // ---------- 阶段 1：从 URL 拿 token ----------
  useEffect(() => {
    const token = searchParams.get('token');
    if (!token || token.length < 20) {
      setState({ kind: 'missing_token' });
    } else {
      setState({ kind: 'ready', token });
    }
  }, [searchParams]);

  /**
   * 阶段 2：调 accept 接口
   *
   * ⚠️ 关键：成功后会再做两件事
   * 1. 重新拉 /tenants/mine（因为 membership 列表变了）
   * 2. 调 /tenants/switch 把 active tenant 切到新工作空间
   * 这样用户接受后直接就在新工作空间的 dashboard 上
   */
  async function onAccept(): Promise<void> {
    if (state.kind !== 'ready') return;
    setAccepting(true);

    try {
      // 1. 接受邀请
      const result = await acceptInvitation(state.token);
      setState({ kind: 'success', data: result });

      // 2. 切到新工作空间
      try {
        const switchResult = await switchTenant(result.joined_tenant.id);
        switchActiveTenant({
          accessToken: switchResult.access_token,
          refreshToken: switchResult.refresh_token,
          activeTenantId: switchResult.active_tenant.id,
        });
      } catch (switchErr) {
        // 切换失败不影响接受成功的状态（用户可以手动切）
        console.warn('Failed to auto-switch tenant:', switchErr);
      }

      // 3. 刷新租户列表
      try {
        await listMyTenants();
      } catch (e) {
        // 列表刷新失败也无所谓
        console.warn('Failed to refresh tenant list:', e);
      }

      // 4. 1.5 秒后跳到 dashboard，让用户看到成功状态
      setTimeout(() => navigate('/dashboard'), 1500);
    } catch (err) {
      const e = err as ApiError;
      setState({
        kind: 'error',
        code: e.code,
        message: e.message || '接受邀请失败',
      });
    } finally {
      setAccepting(false);
    }
  }

  function onLogout(): void {
    clear();
    navigate('/login');
  }

  // ---------- 渲染 ----------

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        {/* ---------- 顶部品牌 ---------- */}
        <div className="mb-6 text-center">
          <h1 className="text-2xl font-semibold text-slate-900">FNAI</h1>
          <p className="mt-1 text-sm text-slate-500">接受邀请</p>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6">
          {/* ---------- 加载中 ---------- */}
          {state.kind === 'loading' && (
            <div className="py-4 text-center text-sm text-slate-500">加载中…</div>
          )}

          {/* ---------- 缺少 token 参数 ---------- */}
          {state.kind === 'missing_token' && (
            <div>
              <div className="mb-2 text-base font-semibold text-red-700">邀请链接无效</div>
              <p className="mb-4 text-sm text-slate-600">
                该链接缺少邀请 token。请检查你收到的链接是否完整。
              </p>
              <button
                onClick={() => navigate('/dashboard')}
                className="w-full rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800"
              >
                返回工作台
              </button>
            </div>
          )}

          {/* ---------- 准备好了，等用户点接受 ---------- */}
          {state.kind === 'ready' && (
            <div>
              <div className="mb-2 text-base font-semibold text-slate-900">你收到了一条邀请！</div>
              <p className="mb-4 text-sm text-slate-600">
                你好 <strong>{user?.email}</strong>，点击下方按钮即可接受邀请并加入工作空间。
              </p>
              <div className="mb-4 rounded-md border border-slate-200 bg-slate-50 p-3">
                <div className="text-xs text-slate-500">邀请 token</div>
                <code className="break-all font-mono text-xs text-slate-700">
                  {state.token.slice(0, 20)}…
                </code>
              </div>
              <button
                onClick={onAccept}
                disabled={accepting}
                className="w-full rounded-md bg-slate-900 px-4 py-2 font-medium text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {accepting ? '接受中…' : '接受邀请'}
              </button>
            </div>
          )}

          {/* ---------- 成功状态 ---------- */}
          {state.kind === 'success' && (
            <div>
              <div className="mb-2 text-base font-semibold text-emerald-700">✅ 邀请已接受！</div>
              <p className="mb-2 text-sm text-slate-600">
                你已加入 <strong>{state.data.joined_tenant.name}</strong>，角色为{' '}
                <strong>{state.data.joined_tenant.role}</strong>。
              </p>
              <p className="text-xs text-slate-500">即将跳转到工作台…</p>
            </div>
          )}

          {/* ---------- 错误状态 ---------- */}
          {state.kind === 'error' && (
            <div>
              <div className="mb-2 text-base font-semibold text-red-700">
                {state.code === 'email_mismatch'
                  ? '账号不匹配'
                  : state.code === 'token_expired'
                    ? '邀请已过期'
                    : state.code === 'token_used'
                      ? '邀请已被使用'
                      : state.code === 'token_revoked'
                        ? '邀请已被撤销'
                        : '接受失败'}
              </div>
              <p className="mb-4 text-sm text-slate-600">{state.message}</p>
              {state.code === 'email_mismatch' && (
                <p className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
                  该邀请是发给其他邮箱的。请退出登录，然后用收到邀请的那个邮箱重新登录。
                </p>
              )}
              <div className="flex gap-2">
                <button
                  onClick={() => navigate('/dashboard')}
                  className="flex-1 rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800"
                >
                  返回工作台
                </button>
                {state.code === 'email_mismatch' && (
                  <button
                    onClick={onLogout}
                    className="flex-1 rounded-md border border-slate-300 px-4 py-2 font-medium text-slate-700 hover:bg-slate-50"
                  >
                    退出登录
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* ---------- 底部链接 ---------- */}
        <div className="mt-4 text-center">
          <button
            onClick={() => navigate('/dashboard')}
            className="text-xs text-slate-500 hover:text-slate-700"
          >
            ← 返回工作台
          </button>
        </div>
      </div>
    </div>
  );
}
