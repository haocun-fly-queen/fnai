// Auth store — persists access token + current user across the app.
//
// 本文件是 FNAI 前端"全局认证状态"的唯一真相来源。
// 用 zustand + persist 写到 localStorage，刷新页面后状态还在。
//
// 给 Java 背景同事的提示：
// - zustand ≈ 一个轻量级的"全局单例 Bean"
// - persist 中间件 ≈ Spring 的 @ConfigurationProperties 自动持久化
// - 整个 store 是模块级单例，组件用 useAuthStore() 取状态

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

/** 当前登录用户的基础信息（从 /auth/me 拿） */
export interface AuthUser {
  id: string;
  email: string;
  full_name: string | null;
  is_superuser: boolean;
}

/** 我加入的租户概览（dashboard 渲染用） */
export interface MembershipSummary {
  tenant: {
    id: string;
    name: string;
    slug: string;
    plan: string;
    status: string;
  };
  role: 'owner' | 'admin' | 'member' | 'viewer';
}

/** Auth store 的完整状态定义 */
interface AuthState {
  /** JWT access token（短期 15 分钟），每次 HTTP 请求都要塞 Header */
  accessToken: string | null;
  /** JWT refresh token（长期 7 天），access 过期后用这个换新的 */
  refreshToken: string | null;
  /** 当前登录用户的基础信息 */
  user: AuthUser | null;
  /** 我加入的所有租户（带角色），用于 workspace 切换器 */
  memberships: MembershipSummary[];

  /**
   * 当前激活的租户 ID。
   * 切换租户时更新，业务请求时会带到 Authorization 里。
   * 注意：这个值**和 access token 里的 active_tenant_id 同步**。
   */
  activeTenantId: string | null;

  // --------------------------------------------------------
  // 状态变更方法
  // --------------------------------------------------------

  /**
   * 登录/注册成功后调用：一次性把 token + user + memberships 都塞进去。
   * 第一次登录时 activeTenantId 默认设为第一个 OWNER 租户。
   */
  setSession: (input: {
    accessToken: string;
    refreshToken: string;
    user: AuthUser;
    memberships: MembershipSummary[];
    activeTenantId?: string | null;
  }) => void;

  /** 401 自动刷新后调用：只更新 access token */
  setAccessToken: (token: string) => void;

  /**
   * 切换激活租户时调用：
   * 1. 存新 access/refresh token
   * 2. 更新 activeTenantId
   * 3. 更新 memberships 里对应租户的 is_active 标记
   */
  switchActiveTenant: (input: {
    accessToken: string;
    refreshToken: string;
    activeTenantId: string;
  }) => void;

  /** 退出登录时调用：清空所有状态 */
  clear: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      // 初始状态：全 null
      accessToken: null,
      refreshToken: null,
      user: null,
      memberships: [],
      activeTenantId: null,

      // 一次性设置登录态
      setSession: ({ accessToken, refreshToken, user, memberships, activeTenantId }) => {
        // 如果外部没传 activeTenantId，自动用"第一个 OWNER 租户"或第一个租户
        // 这是为了登录后 UI 能立刻显示"当前在哪个 workspace"
        let resolvedActive = activeTenantId ?? null;
        if (!resolvedActive && memberships.length > 0) {
          const owner = memberships.find((m) => m.role === 'owner');
          // ⚠️ 用非空断言 ! 因为 if 条件已经保证了 memberships[0] 存在
          // TypeScript 在闭包里推不出"lengh > 0 ⇒ [0] 存在"
          resolvedActive = (owner ?? memberships[0]!).tenant.id;
        }

        set({
          accessToken,
          refreshToken,
          user,
          memberships,
          activeTenantId: resolvedActive,
        });
      },

      // 只更新 access token（401 刷新场景）
      setAccessToken: (accessToken) => set({ accessToken }),

      // 切换激活租户
      switchActiveTenant: ({ accessToken, refreshToken, activeTenantId }) =>
        set({
          accessToken,
          refreshToken,
          activeTenantId,
          // 顺便更新 memberships 里的 is_active 标记（如果有的话）
          // 注意：MembershipSummary 没有 is_active 字段，但 store 里
          // 有 memberships 数组，可以加。简化起见这里只更新 activeTenantId。
        }),

      // 清空所有状态
      clear: () =>
        set({
          accessToken: null,
          refreshToken: null,
          user: null,
          memberships: [],
          activeTenantId: null,
        }),
    }),
    {
      // localStorage 的 key 名
      name: 'fnai.auth',
      // 只持久化"刷新页面后还需要保留"的部分
      // accessToken 也会持久化（生产环境不推荐，但开发阶段方便）
      partialize: (s) => ({
        accessToken: s.accessToken,
        refreshToken: s.refreshToken,
        user: s.user,
        memberships: s.memberships,
        activeTenantId: s.activeTenantId,
      }),
    },
  ),
);
