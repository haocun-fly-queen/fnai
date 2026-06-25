// Membership management API client.
//
// 本文件是"成员管理"接口的封装层。
// 3 个函数对应 3 个端点：列成员、改角色、踢人。
//
// 给 Java 背景同事的提示：
// - 这个文件 ≈ Java 的 Feign Client / Retrofit Interface
// - 函数返回 Promise<T> ≈ Java 的 CompletableFuture<T>

import { api } from './api';
import type {
  ChangeRoleRequest,
  ChangeRoleResponse,
  ListMembersResponse,
  RemoveMemberResponse,
} from '../types/api';

/**
 * 列出某租户的所有成员。
 *
 * 后端：GET /tenants/{tenant_id}/members
 * 鉴权：需要任何成员（VIEWER 也能看）
 *
 * Returns:
 *   { items: MemberDetail[], total: number }
 *   - items: 按 role 倒序（OWNER 排前）+ 加入时间升序
 *   - is_current_user: 这个成员是不是当前请求的 user
 *
 * 业务用途：团队管理页"当前成员"列表
 */
export async function listMembers(tenantId: string): Promise<ListMembersResponse> {
  const response = await api.get<ListMembersResponse>(`/tenants/${tenantId}/members`);
  return response.data;
}

/**
 * 修改某成员的角色。
 *
 * 后端：PATCH /tenants/{tenant_id}/members/{user_id}
 * 鉴权：需要 ADMIN+
 *
 * Request body:
 *   { role: "admin" | "member" | "viewer" }  // 不允许 owner
 *
 * Returns:
 *   { user_id, old_role, new_role, message }
 *
 * 业务用途：团队管理页"改角色"下拉菜单
 *
 * 错误：
 * - 400 update_failed: DB 错误
 * - 403 self_role_change: 改自己
 * - 403 permission_denied: 权限不够（ADMIN 改 ADMIN/OWNER）
 * - 404 member_not_found: 目标不是成员
 * - 409 cannot_assign_owner: 试图给 OWNER
 * - 409 downgrade_last_owner: 降级最后 OWNER
 */
export async function changeMemberRole(
  tenantId: string,
  userId: string,
  role: 'admin' | 'member' | 'viewer',
): Promise<ChangeRoleResponse> {
  const payload: ChangeRoleRequest = { role };
  const response = await api.patch<ChangeRoleResponse>(
    `/tenants/${tenantId}/members/${userId}`,
    payload,
  );
  return response.data;
}

/**
 * 从租户移除某成员（踢人）。
 *
 * 后端：DELETE /tenants/{tenant_id}/members/{user_id}
 * 鉴权：需要 ADMIN+
 *
 * Returns:
 *   { removed_user_id, remaining_count, message }
 *
 * 业务用途：团队管理页"踢人"按钮
 *
 * 错误：
 * - 403 self_remove: 踢自己
 * - 403 permission_denied: 权限不够
 * - 404 member_not_found: 不是成员
 * - 409 remove_last_owner: 踢最后 OWNER
 */
export async function removeMember(
  tenantId: string,
  userId: string,
): Promise<RemoveMemberResponse> {
  const response = await api.delete<RemoveMemberResponse>(`/tenants/${tenantId}/members/${userId}`);
  return response.data;
}
