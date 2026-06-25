// Invitation API client.
//
// 本文件是前端调邀请相关接口的"封装层"。
// 4 个函数对应 4 个端点。
//
// 给 Java 背景同事的提示：
// - 这个文件 ≈ Java 的 Feign Client / Retrofit Interface
// - 函数返回 Promise<T> ≈ Java 的 CompletableFuture<T>
// - 错误处理：业务异常用 ApiError，普通网络异常用 Error

import { api } from './api';
import type {
  AcceptInvitationRequest,
  AcceptInvitationResponse,
  CreateInvitationRequest,
  CreateInvitationResponse,
  ListInvitationsResponse,
} from '../types/api';

/**
 * 列出当前激活租户的所有邀请。
 *
 * 后端：GET /invitations
 * 鉴权：需要 OWNER/ADMIN 角色
 *
 * Returns:
 *   { items: Invitation[], active_tenant_id, pending_count, accepted_count }
 *
 * 业务用途：团队管理页"成员邀请"列表
 */
export async function listInvitations(): Promise<ListInvitationsResponse> {
  const response = await api.get<ListInvitationsResponse>('/invitations');
  return response.data;
}

/**
 * 创建一个新邀请。
 *
 * 后端：POST /invitations
 * 鉴权：需要 OWNER/ADMIN 角色
 *
 * Request body:
 *   { email: string, role: "admin" | "member" | "viewer" }
 *   ⚠️ 不允许 role=owner（后端会返回 403 cannot_invite_owner）
 *
 * Returns:
 *   { invitation: Invitation, invite_link: string, token: string }
 *   - invite_link: 完整 URL，前端直接复制发出去
 *   - token: 纯 token，用于二维码/IM 渠道
 *
 * 业务用途：OWNER/ADMIN 在团队管理页填邮箱 + 选角色 → 复制链接发给被邀请者
 */
export async function createInvitation(
  email: string,
  role: 'admin' | 'member' | 'viewer' = 'member',
): Promise<CreateInvitationResponse> {
  const payload: CreateInvitationRequest = { email, role };
  const response = await api.post<CreateInvitationResponse>('/invitations', payload);
  return response.data;
}

/**
 * 撤销一个 pending 邀请。
 *
 * 后端：DELETE /invitations/{id}
 * 鉴权：需要 OWNER/ADMIN 角色
 *
 * 业务用途：邀请发错了 / 对方不需要了 → 撤销
 * 撤销后 token 立即失效
 */
export async function revokeInvitation(invitationId: string): Promise<void> {
  await api.delete(`/invitations/${invitationId}`);
}

/**
 * 接受一个邀请（用 token）。
 *
 * 后端：POST /invitations/accept
 * 鉴权：需要任何已登录用户
 *
 * Request body:
 *   { token: string }  // 从邀请链接 / 邮件里拿
 *
 * Returns:
 *   { invitation, joined_tenant, message }
 *   - joined_tenant: 新加入的租户信息，前端用来跳到新工作空间
 *
 * 业务用途：
 * - 用户点邮件里的接受链接 → 进 accept 页面 → 调这个 → 跳 dashboard
 * - 注册时如果有 pending 邀请会自动接受（不用调这个）
 */
export async function acceptInvitation(token: string): Promise<AcceptInvitationResponse> {
  const payload: AcceptInvitationRequest = { token };
  const response = await api.post<AcceptInvitationResponse>('/invitations/accept', payload);
  return response.data;
}
