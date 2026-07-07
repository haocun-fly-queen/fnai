import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { login } from '@/lib/auth-api';
import { useAuthStore } from '@/stores/auth';
import { fetchMe } from '@/lib/auth-api';
import type { ApiError } from '@/types/api';

export function LoginPage(): JSX.Element {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const tokens = await login({ email, password });

      // 先用临时数据设置 token，以便 fetchMe 能正常调用
      setSession({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        user: { id: '', email, full_name: null, is_superuser: false },
        memberships: [],
      });

      // Pull the real user + memberships with the new token.
      const me = await fetchMe();

      // 自动选择第一个 OWNER 租户作为激活租户，如果没有 OWNER 则选择第一个租户
      let activeTenantId: string | undefined;
      if (me.memberships.length > 0) {
        const ownerMembership = me.memberships.find((m) => m.role === 'owner');
        activeTenantId = ownerMembership?.tenant.id || me.memberships[0].tenant.id;
      }

      setSession({
        accessToken: tokens.access_token,
        refreshToken: tokens.refresh_token,
        user: {
          id: me.user.id,
          email: me.user.email,
          full_name: me.user.full_name,
          is_superuser: me.user.is_superuser,
        },
        memberships: me.memberships,
        activeTenantId, // 设置激活的租户 ID
      });

      navigate('/dashboard');
    } catch (err) {
      const apiErr = err as ApiError;
      setError(apiErr.message || '登录失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        <h1 className="mb-8 text-center text-2xl font-semibold text-slate-900">FNAI</h1>

        <form onSubmit={onSubmit} className="space-y-4">
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-slate-700">
              邮箱
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
          </div>

          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-slate-700">
              密码
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-slate-900"
            />
          </div>

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-slate-900 px-4 py-2 font-medium text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? '登录中…' : '登录'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          还没有账号？{' '}
          <Link to="/register" className="font-medium text-slate-900 hover:underline">
            立即注册
          </Link>
        </p>
      </div>
    </div>
  );
}
