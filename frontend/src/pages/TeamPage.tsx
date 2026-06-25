// TeamPage —— 团队管理页（邀请 + 成员列表 + 历史邀请）。
//
// 这个页面是 FNAI 多租户协作的"主控制台"：
// - 创建邀请（OWNER/ADMIN）
// - 撤销邀请（OWNER/ADMIN）
// - 列出当前成员（任何人）
// - 改角色（ADMIN+，且不能改 OWNER/同等级）
// - 踢人（ADMIN+，且不能踢 OWNER/同等级）
//
// 给 Java 背景同事的提示：
// - 这相当于 Spring 的 @Controller 渲染团队管理视图
// - useEffect 触发拉数据 ≈ @PostConstruct
// - 整个页面是"受控的"：所有状态都在 zustand 或者 useState 里
// - 改角色/踢人需要二次确认（弹 confirm 对话框）

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth';
import { fetchMe } from '@/lib/auth-api';
import { createInvitation, listInvitations, revokeInvitation } from '@/lib/invitation-api';
import { changeMemberRole, listMembers, removeMember } from '@/lib/membership-api';
import type {
  CreateInvitationResponse,
  Invitation,
  InvitationStatus,
  MemberDetail,
  Role as RoleType,
} from '@/types/api';
import type { ApiError } from '@/types/api';

// 角色下拉选项（不包含 OWNER，因为不能通过邀请/改角色给）
const ROLE_OPTIONS: Array<{ value: 'admin' | 'member' | 'viewer'; label: string }> = [
  { value: 'admin', label: '管理员（可管理团队）' },
  { value: 'member', label: '成员（正常使用）' },
  { value: 'viewer', label: '访客（只读）' },
];

export function TeamPage(): JSX.Element {
  const navigate = useNavigate();
  const { user, activeTenantId, clear } = useAuthStore();

  // ---------- 状态 ----------

  // 邀请列表
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [acceptedCount, setAcceptedCount] = useState(0);

  // 成员列表（从 /tenants/{id}/members 拉，含 user.email 和 is_current_user）
  const [members, setMembers] = useState<MemberDetail[]>([]);

  // 当前用户在这个租户的角色（决定能不能改/踢人）
  const currentMember = members.find((m) => m.user_id === user?.id);
  const myRole = currentMember?.role;

  // 邀请表单
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<RoleType>('member');
  const [submitting, setSubmitting] = useState(false);

  // 刚创建的邀请响应
  const [lastCreated, setLastCreated] = useState<CreateInvitationResponse | null>(null);

  // 错误 / 成功
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // 当前正在操作的成员（用于显示 loading）
  const [operating, setOperating] = useState<string | null>(null);

  // ---------- 加载数据 ----------

  useEffect(() => {
    if (!activeTenantId) return;
    let cancelled = false;

    async function load(): Promise<void> {
      try {
        // 并行拉：邀请 + 成员 + me
        const [invResp, memResp, me] = await Promise.all([
          listInvitations(),
          listMembers(activeTenantId!),
          fetchMe(),
        ]);
        if (cancelled) return;

        setInvitations(invResp.items);
        setPendingCount(invResp.pending_count);
        setAcceptedCount(invResp.accepted_count);
        setMembers(memResp.items);
        // me 数据备用（虽然没直接用，但保证 store 是新的）
        void me;
      } catch (err) {
        if (cancelled) return;
        const e = err as ApiError;
        setError(e.message || '加载团队数据失败');
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [activeTenantId]);

  // ---------- 权限辅助 ----------

  /**
   * 我能不能改/踢某个成员？
   *
   * 规则（从后端 service 镜像过来）：
   * 1. 我是 OWNER → 任何人（除自己）
   * 2. 我是 ADMIN → 等级比我低的（MEMBER/VIEWER），且不是自己
   * 3. 我是 MEMBER/VIEWER → 谁都不能
   * 4. 不能改/踢 OWNER（除非我是 OWNER）
   */
  function canIManage(target: MemberDetail): boolean {
    if (!myRole || target.user_id === user?.id) return false; // 不能改自己
    if (myRole === 'owner') return true; // OWNER 啥都能
    if (myRole === 'admin') {
      // ADMIN 只能动 MEMBER/VIEWER
      return target.role === 'member' || target.role === 'viewer';
    }
    return false; // MEMBER/VIEWER 没权限
  }

  function canIChangeRole(target: MemberDetail): boolean {
    // 同 canIManage，但额外：不能改 OWNER（即使是 OWNER 自己）
    // 实际上 OWNER 可以改其他 OWNER（极端情况），但不允许
    // 简单起见：跟 canIManage 一致
    return canIManage(target);
  }

  // ---------- 处理函数 ----------

  /**
   * 提交邀请表单。
   */
  async function onSubmitInvite(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!email || submitting) return;

    setError(null);
    setLastCreated(null);
    setCopied(false);
    setSubmitting(true);

    try {
      const safeRole: 'admin' | 'member' | 'viewer' = role === 'owner' ? 'member' : role;
      const result = await createInvitation(email, safeRole);
      setLastCreated(result);
      setEmail('');

      const list = await listInvitations();
      setInvitations(list.items);
      setPendingCount(list.pending_count);
      setAcceptedCount(list.accepted_count);
    } catch (err) {
      const e = err as ApiError;
      setError(e.message || '创建邀请失败');
    } finally {
      setSubmitting(false);
    }
  }

  /**
   * 撤销邀请。
   */
  async function onRevoke(id: string): Promise<void> {
    if (!confirm('确定要撤销这条邀请吗？')) return;
    try {
      await revokeInvitation(id);
      const list = await listInvitations();
      setInvitations(list.items);
      setPendingCount(list.pending_count);
      setAcceptedCount(list.accepted_count);
    } catch (err) {
      const e = err as ApiError;
      setError(e.message || '撤销失败');
    }
  }

  /**
   * 复制 invite_link。
   */
  async function onCopyLink(): Promise<void> {
    if (!lastCreated) return;
    try {
      await navigator.clipboard.writeText(lastCreated.invite_link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('复制链接失败');
    }
  }

  /**
   * 改变成员角色。
   *
   * 用浏览器 confirm 做二次确认（避免误点）。
   */
  async function onChangeRole(
    target: MemberDetail,
    newRole: 'admin' | 'member' | 'viewer',
  ): Promise<void> {
    if (!confirm(`确定要把 ${target.user.email} 的角色从 ${target.role} 改为 ${newRole} 吗？`)) {
      return;
    }
    setOperating(target.user_id);
    setError(null);
    try {
      await changeMemberRole(activeTenantId!, target.user_id, newRole);
      // 刷新成员列表
      const mem = await listMembers(activeTenantId!);
      setMembers(mem.items);
    } catch (err) {
      const e = err as ApiError;
      setError(e.message || '修改角色失败');
    } finally {
      setOperating(null);
    }
  }

  /**
   * 踢人。
   *
   * 二次确认（更严格的提示）。
   */
  async function onKick(target: MemberDetail): Promise<void> {
    if (!confirm(`确定要把 ${target.user.email} 移出该工作空间吗？对方将立即失去访问权限。`)) {
      return;
    }
    setOperating(target.user_id);
    setError(null);
    try {
      await removeMember(activeTenantId!, target.user_id);
      const mem = await listMembers(activeTenantId!);
      setMembers(mem.items);
    } catch (err) {
      const e = err as ApiError;
      setError(e.message || '移除成员失败');
    } finally {
      setOperating(null);
    }
  }

  function onLogout(): void {
    clear();
    navigate('/login');
  }

  // ---------- 派生数据 ----------

  const pendingInvitations = invitations.filter((i) => i.status === 'pending');
  const historyInvitations = invitations.filter((i) => i.status !== 'pending');

  // 当前 tenant（取 members 的第一个的 tenant 名字，但实际 display 用 activeTenantId）
  const myDisplayMember = members.find((m) => m.is_current_user);

  // ---------- 渲染 ----------

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ---------- 顶部导航 ---------- */}
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <h1 className="text-lg font-semibold text-slate-900">FNAI</h1>
            <span className="text-sm text-slate-500">/ 团队管理</span>
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

      <main className="mx-auto max-w-3xl space-y-6 px-6 py-8">
        {/* ---------- 错误信息条 ---------- */}
        {error && (
          <section className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </section>
        )}

        {/* ---------- 当前用户角色提示 ---------- */}
        {myDisplayMember && (
          <section className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-900">
            你在这个工作空间是 <strong className="uppercase">{myDisplayMember.role}</strong>。
            {myRole === 'owner' && ' 你可以管理所有成员和租户设置。'}
            {myRole === 'admin' && ' 你可以邀请成员、踢 MEMBER/VIEWER、给他们改角色。'}
            {myRole === 'member' && ' 你只能邀请成员（不能改/踢）。'}
            {myRole === 'viewer' && ' 你只能查看（不能改/踢/邀请）。'}
          </section>
        )}

        {/* ---------- 邀请表单 ---------- */}
        {(myRole === 'owner' || myRole === 'admin') && (
          <section className="rounded-lg border border-slate-200 bg-white p-6">
            <h2 className="mb-1 text-base font-semibold text-slate-900">邀请新成员</h2>
            <p className="mb-4 text-sm text-slate-500">
              对方会收到一条接受邀请的链接，链接 7 天后失效。
            </p>

            <form onSubmit={onSubmitInvite} className="space-y-3">
              <div>
                <label
                  htmlFor="invite-email"
                  className="mb-1 block text-sm font-medium text-slate-700"
                >
                  邮箱
                </label>
                <input
                  id="invite-email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="colleague@example.com"
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-slate-900"
                />
              </div>

              <div>
                <label
                  htmlFor="invite-role"
                  className="mb-1 block text-sm font-medium text-slate-700"
                >
                  角色
                </label>
                <select
                  id="invite-role"
                  value={role}
                  onChange={(e) => setRole(e.target.value as RoleType)}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-slate-900"
                >
                  {ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <button
                type="submit"
                disabled={submitting || !email}
                className="w-full rounded-md bg-slate-900 px-4 py-2 font-medium text-white transition-colors hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? '创建中…' : '创建邀请'}
              </button>
            </form>

            {lastCreated && (
              <div className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 p-4">
                <div className="mb-2 text-sm font-medium text-emerald-900">
                  ✅ 邀请已创建！请分享以下链接：
                </div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 break-all rounded border border-emerald-200 bg-white px-2 py-1.5 font-mono text-xs">
                    {lastCreated.invite_link}
                  </code>
                  <button
                    onClick={onCopyLink}
                    className="rounded bg-emerald-700 px-3 py-1.5 text-xs text-white hover:bg-emerald-800"
                  >
                    {copied ? '已复制！' : '复制'}
                  </button>
                </div>
                <div className="mt-2 text-xs text-emerald-700">
                  发送给：{lastCreated.invitation.email}，角色为{' '}
                  <strong>{lastCreated.invitation.role}</strong>
                </div>
              </div>
            )}
          </section>
        )}

        {/* ---------- 成员列表（带操作）---------- */}
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-900">成员（{members.length}）</h2>
          </div>

          {members.length === 0 ? (
            <p className="text-sm text-slate-500">加载中…</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {members.map((m) => (
                <MemberRow
                  key={m.user_id}
                  member={m}
                  canManage={canIManage(m)}
                  canChangeRole={canIChangeRole(m)}
                  operating={operating === m.user_id}
                  onChangeRole={onChangeRole}
                  onKick={onKick}
                />
              ))}
            </ul>
          )}
        </section>

        {/* ---------- 待处理邀请 ---------- */}
        {pendingInvitations.length > 0 && (
          <section className="rounded-lg border border-slate-200 bg-white p-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-900">待处理邀请</h2>
              <span className="text-xs text-slate-500">待处理 {pendingCount} 条</span>
            </div>
            <ul className="divide-y divide-slate-100">
              {pendingInvitations.map((inv) => (
                <InvitationRow key={inv.id} invitation={inv} onRevoke={onRevoke} />
              ))}
            </ul>
          </section>
        )}

        {/* ---------- 历史邀请 ---------- */}
        {historyInvitations.length > 0 && (
          <section className="rounded-lg border border-slate-200 bg-white p-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-base font-semibold text-slate-900">历史邀请</h2>
              <span className="text-xs text-slate-500">已接受 {acceptedCount} 条</span>
            </div>
            <ul className="divide-y divide-slate-100">
              {historyInvitations.map((inv) => (
                <InvitationRow key={inv.id} invitation={inv} onRevoke={onRevoke} />
              ))}
            </ul>
          </section>
        )}
      </main>
    </div>
  );
}

// ============================================================
// 子组件：单个成员（带操作）
// ============================================================

function MemberRow({
  member,
  canManage,
  canChangeRole,
  operating,
  onChangeRole,
  onKick,
}: {
  member: MemberDetail;
  canManage: boolean;
  canChangeRole: boolean;
  operating: boolean;
  onChangeRole: (m: MemberDetail, newRole: 'admin' | 'member' | 'viewer') => void;
  onKick: (m: MemberDetail) => void;
}): JSX.Element {
  // 角色对应的颜色
  const roleColor: Record<RoleType, string> = {
    owner: 'bg-amber-100 text-amber-800',
    admin: 'bg-purple-100 text-purple-800',
    member: 'bg-blue-100 text-blue-800',
    viewer: 'bg-slate-100 text-slate-700',
  };

  // 改角色的可选目标（不能改成 OWNER；不能改成自己当前的）
  const targetRoles: Array<'admin' | 'member' | 'viewer'> = ['admin', 'member', 'viewer'].filter(
    (r) => r !== member.role,
  ) as Array<'admin' | 'member' | 'viewer'>;

  return (
    <li className="flex items-center justify-between gap-3 py-3">
      {/* ---------- 用户信息 ---------- */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-slate-900">{member.user.email}</span>
          {member.is_current_user && (
            <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] text-slate-600">
              （你）
            </span>
          )}
          <span className={`rounded px-1.5 py-0.5 text-xs ${roleColor[member.role]}`}>
            {member.role}
          </span>
        </div>
        {member.user.full_name && (
          <div className="mt-0.5 text-xs text-slate-500">{member.user.full_name}</div>
        )}
      </div>

      {/* ---------- 操作按钮（只有 canManage 才显示）---------- */}
      {canManage && !member.is_current_user && (
        <div className="flex items-center gap-2">
          {/* 改角色下拉 */}
          {canChangeRole && (
            <select
              disabled={operating}
              value={member.role}
              onChange={(e) =>
                onChangeRole(member, e.target.value as 'admin' | 'member' | 'viewer')
              }
              className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 hover:border-slate-400 disabled:opacity-50"
              title="修改角色"
            >
              <option value={member.role} disabled>
                {member.role}…
              </option>
              {targetRoles.map((r) => (
                <option key={r} value={r}>
                  → {r}
                </option>
              ))}
            </select>
          )}

          {/* 踢人按钮 */}
          <button
            onClick={() => onKick(member)}
            disabled={operating}
            className="rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50"
            title="移出工作空间"
          >
            {operating ? '…' : '踢出'}
          </button>
        </div>
      )}
    </li>
  );
}

// ============================================================
// 子组件：单条邀请
// ============================================================

function InvitationRow({
  invitation,
  onRevoke,
}: {
  invitation: Invitation;
  onRevoke: (id: string) => void;
}): JSX.Element {
  const statusColor: Record<InvitationStatus, string> = {
    pending: 'bg-amber-100 text-amber-800',
    accepted: 'bg-emerald-100 text-emerald-800',
    expired: 'bg-slate-200 text-slate-600',
    revoked: 'bg-red-100 text-red-800',
  };

  // 状态对应的中文文案
  const statusLabel: Record<InvitationStatus, string> = {
    pending: '待接受',
    accepted: '已接受',
    expired: '已过期',
    revoked: '已撤销',
  };

  const expiresAt = new Date(invitation.expires_at);
  const expiresStr = expiresAt.toLocaleDateString();

  return (
    <li className="flex items-center justify-between py-3">
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-slate-900">{invitation.email}</span>
          <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-700">
            {invitation.role}
          </span>
          <span className={`rounded px-1.5 py-0.5 text-xs ${statusColor[invitation.status]}`}>
            {statusLabel[invitation.status]}
          </span>
        </div>
        <div className="mt-0.5 text-xs text-slate-500">
          {invitation.status === 'pending' && `${expiresStr} 到期`}
          {invitation.status === 'accepted' &&
            invitation.accepted_at &&
            `已于 ${new Date(invitation.accepted_at).toLocaleDateString()} 接受`}
          {invitation.status === 'revoked' &&
            invitation.revoked_at &&
            `已于 ${new Date(invitation.revoked_at).toLocaleDateString()} 撤销`}
          {invitation.status === 'expired' && `${expiresStr} 已过期`}
        </div>
      </div>

      {invitation.status === 'pending' && (
        <button
          onClick={() => onRevoke(invitation.id)}
          className="rounded border border-red-200 px-2 py-1 text-xs text-red-700 hover:bg-red-50"
        >
          撤销
        </button>
      )}
    </li>
  );
}
