/**
 * 发布相关 API（阶段 5）—— 发布目标管理 + 文章发布 + 微信公众号
 */

import type { ApiError } from '@/types/api';

const API_BASE = '/api/v1';

// ============================================================
// 类型定义
// ============================================================

export type PublishTargetType = 'wordpress' | 'webhook';
export type PublishStatus = 'pending' | 'success' | 'failed';

// 微信公众号相关类型
export interface WechatConfig {
  id: string;
  name: string;
  app_id: string;
  author?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WechatConfigCreate {
  name: string;
  app_id: string;
  app_secret: string;
  author?: string;
  thumb_media_id?: string;
}

export interface WechatConfigUpdate {
  name?: string;
  app_secret?: string;
  author?: string;
  thumb_media_id?: string;
}

export interface WechatPublishRequest {
  article_id: string;
  author?: string;
  digest?: string;
  thumb_media_id?: string;
  need_open_comment?: boolean;
  only_fans_can_comment?: boolean;
}

export interface WechatPublishResponse {
  success: boolean;
  message: string;
  publish_id?: string;
  draft_media_id?: string;
  fallback?: boolean;
  fallback_strategy?: string;
  copy_content?: string;
}

export interface WechatPublishStatus {
  publish_id: string;
  publish_status: number;
  article_id?: string;
  article_url?: string;
  fail_reason?: string;
}

export interface PublishTarget {
  id: string;
  tenant_id: string;
  name: string;
  type: PublishTargetType;
  config: Record<string, any>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PublishTargetCreate {
  name: string;
  type: PublishTargetType;
  config: Record<string, any>;
  is_active?: boolean;
}

export interface PublishTargetUpdate {
  name?: string;
  config?: Record<string, any>;
  is_active?: boolean;
}

export interface PublishRequest {
  target_id: string;
  status?: string; // WordPress: draft / publish
}

export interface PublishResponse {
  success: boolean;
  message: string;
  remote_id?: string;
  log_id?: string;
}

export interface PublishLog {
  id: string;
  article_id: string;
  target_id: string;
  status: PublishStatus;
  remote_id?: string;
  error_message?: string;
  published_at: string;
  created_by?: string;
  target_name?: string;
  article_title?: string;
}

// ============================================================
// 发布目标 CRUD
// ============================================================

export async function listPublishTargets(activeOnly = true): Promise<PublishTarget[]> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/publish-targets?active_only=${activeOnly}`, {
    headers: { Authorization: `Bearer ${auth.accessToken}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '获取发布目标失败');
  }

  return res.json();
}

export async function createPublishTarget(data: PublishTargetCreate): Promise<PublishTarget> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/publish-targets`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.accessToken}`,
    },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '创建发布目标失败');
  }

  return res.json();
}

export async function updatePublishTarget(id: string, data: PublishTargetUpdate): Promise<PublishTarget> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/publish-targets/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.accessToken}`,
    },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '更新发布目标失败');
  }

  return res.json();
}

export async function deletePublishTarget(id: string): Promise<void> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/publish-targets/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${auth.accessToken}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '删除发布目标失败');
  }
}

// ============================================================
// 文章发布
// ============================================================

export async function publishArticle(articleId: string, data: PublishRequest): Promise<PublishResponse> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/articles/${articleId}/publish`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.accessToken}`,
    },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '发布失败');
  }

  return res.json();
}

export async function getPublishLogs(articleId: string): Promise<PublishLog[]> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/articles/${articleId}/publish-logs`, {
    headers: { Authorization: `Bearer ${auth.accessToken}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '获取发布历史失败');
  }

  return res.json();
}

// ============================================================
// 导出
// ============================================================

export async function exportArticle(articleId: string, format: 'markdown' | 'html'): Promise<Blob> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/articles/${articleId}/export?format=${format}`, {
    headers: { Authorization: `Bearer ${auth.accessToken}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '导出失败');
  }

  return res.blob();
}

// ============================================================
// 微信公众号配置管理
// ============================================================

export async function listWechatConfigs(): Promise<WechatConfig[]> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/wechat/wechat-configs`, {
    headers: { Authorization: `Bearer ${auth.accessToken}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '获取微信公众号配置失败');
  }

  return res.json();
}

export async function createWechatConfig(data: WechatConfigCreate): Promise<WechatConfig> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/wechat/wechat-configs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.accessToken}`,
    },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '创建微信公众号配置失败');
  }

  return res.json();
}

export async function updateWechatConfig(id: string, data: WechatConfigUpdate): Promise<WechatConfig> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/wechat/wechat-configs/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.accessToken}`,
    },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '更新微信公众号配置失败');
  }

  return res.json();
}

export async function deleteWechatConfig(id: string): Promise<void> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/wechat/wechat-configs/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${auth.accessToken}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '删除微信公众号配置失败');
  }
}

// ============================================================
// 微信公众号发布
// ============================================================

export async function publishToWechat(data: WechatPublishRequest): Promise<WechatPublishResponse> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/wechat/articles/${data.article_id}/publish-wechat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${auth.accessToken}`,
    },
    body: JSON.stringify(data),
  });

  // 即使返回 400 也可能有降级内容，需要解析响应
  const result = await res.json();

  if (!res.ok && !result.fallback) {
    throw new Error(result.message || '发布到微信公众号失败');
  }

  return result;
}

export async function getWechatPublishStatus(publishId: string): Promise<WechatPublishStatus> {
  const token = localStorage.getItem('fnai.auth');
  if (!token) throw new Error('未登录');
  const auth = JSON.parse(token);

  const res = await fetch(`${API_BASE}/wechat/publish-wechat/status/${publishId}`, {
    headers: { Authorization: `Bearer ${auth.accessToken}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '查询微信发布状态失败');
  }

  return res.json();
}
