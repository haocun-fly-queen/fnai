// Tenant HTTP API client.
//
// 本文件是前端调租户相关接口的"封装层"。
// 把 axios 调用包装成 TypeScript 函数，业务层调起来更顺手。
//
// 给 Java 背景同事的提示：
// - 这个文件 ≈ Java 的 Feign Client / Retrofit Interface
// - 函数返回 Promise<T> ≈ Java 的 CompletableFuture<T>
// - 错误处理：业务异常用 ApiError，普通网络异常用 Error

import type { MyTenantsResponse, TenantSwitchRequest, TenantSwitchResponse } from '../types/api';

// 复用 lib/api.ts 的 axios 实例
// 这样自动 401 刷新、请求拦截器都继承过来
import { api } from './api';

/**
 * 列出我加入的所有租户。
 *
 * 后端：GET /tenants/mine
 * 鉴权：需要 Bearer token
 *
 * Returns:
 *   { items: TenantWithMembership[], active_tenant_id: string | null }
 *
 * 业务用途：
 * - dashboard 加载时调用，渲染 workspace 切换器
 * - 切换租户成功后调用，刷新 UI 标记
 */
export async function listMyTenants(): Promise<MyTenantsResponse> {
  const response = await api.get<MyTenantsResponse>('/tenants/mine');
  return response.data;
}

/**
 * 切换当前激活的租户。
 *
 * 后端：POST /tenants/switch
 * 鉴权：需要 Bearer token
 *
 * Request body:
 *   { tenant_id: string }  // 目标租户 UUID
 *
 * Returns:
 *   { access_token, refresh_token, expires_in, active_tenant: TenantWithMembership }
 *
 * 业务用途：
 * - 用户在 workspace 切换器里点击"切换到 X 租户"时调用
 * - 成功后用响应里的新 token + activeTenantId 更新 zustand store
 *
 * 错误：
 * - 404 tenant_not_found：租户 ID 输错了
 * - 403 not_a_member：用户不是这个租户的成员
 * - 409 tenant_inactive：租户被停用
 */
export async function switchTenant(tenantId: string): Promise<TenantSwitchResponse> {
  // 后端期望 snake_case 字段名
  const payload: TenantSwitchRequest = { tenant_id: tenantId };
  const response = await api.post<TenantSwitchResponse>('/tenants/switch', payload);
  return response.data;
}
