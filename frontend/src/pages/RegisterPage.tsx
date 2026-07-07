import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { register, fetchMe } from '@/lib/auth-api';
import { useAuthStore } from '@/stores/auth';
import type { ApiError } from '@/types/api';

export function RegisterPage(): JSX.Element {
  const navigate = useNavigate();
  const setSession = useAuthStore((s) => s.setSession);

  const [form, setForm] = useState({
    email: '',
    password: '',
    full_name: '',
    tenant_name: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function update<K extends keyof typeof form>(key: K, value: string): void {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const { accessToken, refreshToken } = await register(form);

      // 先设置 token 以便调用 fetchMe
      setSession({
        accessToken,
        refreshToken,
        user: { id: '', email: form.email, full_name: form.full_name, is_superuser: false },
        memberships: [],
      });

      const me = await fetchMe();

      // 注册后自动选择第一个租户（通常是新创建的租户）
      let activeTenantId: string | undefined;
      if (me.memberships.length > 0) {
        const ownerMembership = me.memberships.find((m) => m.role === 'owner');
        activeTenantId = ownerMembership?.tenant.id || me.memberships[0].tenant.id;
      }

      setSession({
        accessToken,
        refreshToken,
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
      setError(apiErr.message || '注册失败');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4 py-12">
      <div className="w-full max-w-sm">
        <h1 className="mb-2 text-center text-2xl font-semibold text-slate-900">FNAI</h1>
        <p className="mb-8 text-center text-sm text-slate-600">创建你的工作空间</p>

        <form onSubmit={onSubmit} className="space-y-4">
          <Field
            id="full_name"
            label="姓名"
            value={form.full_name}
            onChange={(v) => update('full_name', v)}
            required
            autoComplete="name"
          />
          <Field
            id="email"
            label="邮箱"
            type="email"
            value={form.email}
            onChange={(v) => update('email', v)}
            required
            autoComplete="email"
          />
          <Field
            id="password"
            label="密码"
            type="password"
            value={form.password}
            onChange={(v) => update('password', v)}
            required
            minLength={8}
            autoComplete="new-password"
          />
          <Field
            id="tenant_name"
            label="工作空间名称"
            value={form.tenant_name}
            onChange={(v) => update('tenant_name', v)}
            required
            placeholder="我的公司"
          />

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
            {submitting ? '创建中…' : '创建账号'}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-slate-600">
          已有账号？{' '}
          <Link to="/login" className="font-medium text-slate-900 hover:underline">
            立即登录
          </Link>
        </p>
      </div>
    </div>
  );
}

interface FieldProps {
  id: string;
  label: string;
  type?: string;
  value: string;
  onChange: (v: string) => void;
  required?: boolean;
  minLength?: number;
  autoComplete?: string;
  placeholder?: string;
}

function Field({
  id,
  label,
  type = 'text',
  value,
  onChange,
  required,
  minLength,
  autoComplete,
  placeholder,
}: FieldProps): JSX.Element {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block text-sm font-medium text-slate-700">
        {label}
      </label>
      <input
        id={id}
        type={type}
        required={required}
        minLength={minLength}
        autoComplete={autoComplete}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-slate-900"
      />
    </div>
  );
}
