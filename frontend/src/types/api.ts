// Shared TypeScript types mirroring backend Pydantic schemas.
//
// 这个文件是"前后端类型契约"——后端 Pydantic schema 长什么样，
// 前端 TS interface 就长什么样。改一边要记得改另一边。
//
// 给 Java 背景同事的提示：
// - TypeScript 的 interface ≈ Java 的 record 或 POJO
// - 字段名是 snake_case（和后端保持一致）—— 业务代码里访问时
//   IDE 会自动提示，比 Java 的 getter/setter 简洁

export type Role = 'owner' | 'admin' | 'member' | 'viewer';

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  plan: string;
  status: string;
  created_at: string;
}

/**
 * 带"我在这个租户的角色"信息的租户。
 *
 * 用于 /tenants/mine 接口和 /tenants/switch 响应里的 active_tenant。
 * 相比 Tenant 类型，多了 role 和 is_active 字段。
 */
export interface TenantWithMembership extends Tenant {
  role: Role;
  is_active: boolean;
}

/** GET /tenants/mine 响应结构 */
export interface MyTenantsResponse {
  items: TenantWithMembership[];
  active_tenant_id: string | null;
}

/** POST /tenants/switch 请求体 */
export interface TenantSwitchRequest {
  tenant_id: string;
}

/** POST /tenants/switch 响应结构 */
export interface TenantSwitchResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  active_tenant: TenantWithMembership;
}

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  status: string;
  is_superuser: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface Membership {
  tenant: Tenant;
  role: Role;
}

export interface CurrentUserResponse {
  user: User;
  memberships: Membership[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface ApiError {
  code: string;
  message: string;
  detail?: unknown;
}

// ============================================================
// 邀请（Invitation）相关类型
// ============================================================
// ⚠️ 字段名严格对应 backend/app/schemas/invitation.py
// 改后端 schema 时记得同步这里

/** 邀请的状态。派生字段（后端根据 expires_at / accepted_at 实时算） */
export type InvitationStatus = 'pending' | 'accepted' | 'expired' | 'revoked';

/** 邀请的展示数据（GET /invitations 和 POST /invitations 响应里都有） */
export interface Invitation {
  id: string;
  email: string;
  role: Role;
  status: InvitationStatus;
  created_at: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  invited_by_email: string | null;
}

/** POST /invitations 请求体 */
export interface CreateInvitationRequest {
  email: string;
  role: Role;
}

/** POST /invitations 响应（创建后立刻返回，**带** token 和 URL） */
export interface CreateInvitationResponse {
  invitation: Invitation;
  invite_link: string;
  token: string;
}

/** GET /invitations 响应 */
export interface ListInvitationsResponse {
  items: Invitation[];
  active_tenant_id: string | null;
  pending_count: number;
  accepted_count: number;
}

/** POST /invitations/accept 请求体 */
export interface AcceptInvitationRequest {
  token: string;
}

/** POST /invitations/accept 响应 */
export interface AcceptInvitationResponse {
  invitation: Invitation;
  joined_tenant: TenantWithMembership;
  message: string;
}

// ============================================================
// 成员管理（Membership Management）相关类型
// ============================================================

/** GET /tenants/{tenant_id}/members 响应里的单个成员 */
export interface MemberDetail {
  user_id: string;
  role: Role;
  user: {
    id: string;
    email: string;
    full_name: string | null;
    status: string;
  };
  joined_at: string;
  invited_by: string | null;
  is_current_user: boolean;
}

/** GET /tenants/{tenant_id}/members 响应 */
export interface ListMembersResponse {
  items: MemberDetail[];
  total: number;
}

/** PATCH /tenants/{tenant_id}/members/{user_id} 请求体 */
export interface ChangeRoleRequest {
  role: 'admin' | 'member' | 'viewer'; // 不允许 owner
}

/** PATCH 响应 */
export interface ChangeRoleResponse {
  user_id: string;
  old_role: Role;
  new_role: Role;
  message: string;
}

/** DELETE 响应 */
export interface RemoveMemberResponse {
  removed_user_id: string;
  remaining_count: number;
  message: string;
}
