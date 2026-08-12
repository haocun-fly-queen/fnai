/**
 * 发布相关 API（阶段 5）—— 发布目标管理 + 文章发布 + 微信公众号
 */

import type { ApiError } from '@/types/api';
import { api } from './api';

const API_BASE = '/api/v1';

// ============================================================
// Helper: 获取 accessToken（兼容 zustand persist 数据结构）
// ============================================================

function getAccessToken(): string {
  const stored = localStorage.getItem('fnai.auth');
  if (!stored) throw new Error('未登录');

  const parsed = JSON.parse(stored);
  // zustand persist 的格式：{ state: { accessToken, ... }, version: 0 }
  // 兼容直接存储的格式：{ accessToken, ... }
  const token = parsed.state?.accessToken || parsed.accessToken;
  if (!token) throw new Error('Token 无效，请重新登录');

  return token;
}

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
  config_id: string; // 微信公众号配置 ID
  author?: string;
  digest?: string;
  thumb_media_id?: string;
  need_open_comment?: boolean;
  only_fans_can_comment?: boolean;
  push_to_followers?: boolean; // 是否同时群发推送给粉丝
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
  action?: 'created' | 'updated';
}

export interface PublishLog {
  is_published: boolean;
  published_at: string;
  target_name: string;
  target_id?: string;
}

// ============================================================
// 发布目标 CRUD
// ============================================================

export async function listPublishTargets(activeOnly = true): Promise<PublishTarget[]> {
  const token = getAccessToken();

  const res = await fetch(`${API_BASE}/publish-targets?active_only=${activeOnly}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '获取发布目标失败');
  }

  return res.json();
}

export async function createPublishTarget(data: PublishTargetCreate): Promise<PublishTarget> {
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/publish-targets`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
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
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/publish-targets/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
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
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/publish-targets/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
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
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/articles/${articleId}/publish`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '发布失败');
  }

  return res.json();
}

export interface BatchPublishRequest {
  article_ids: string[];
  target_ids: string[];
  status?: string; // WordPress: draft / publish
}

export interface BatchPublishResponse {
  task_count: number;
  article_ids: string[];
  message: string;
}

export async function batchPublish(data: BatchPublishRequest): Promise<BatchPublishResponse> {
  const token = getAccessToken();

  const res = await fetch(`${API_BASE}/articles/batch-publish`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(data),
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '批量发布失败');
  }

  return res.json();
}

export async function getPublishLogs(articleId: string): Promise<PublishLog[]> {
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/articles/${articleId}/publish-logs`, {
    headers: { Authorization: `Bearer ${token}` },
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
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/articles/${articleId}/export?format=${format}`, {
    headers: { Authorization: `Bearer ${token}` },
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
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/wechat/wechat-configs`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '获取微信公众号配置失败');
  }

  return res.json();
}

export async function createWechatConfig(data: WechatConfigCreate): Promise<WechatConfig> {
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/wechat/wechat-configs`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
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
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/wechat/wechat-configs/${id}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
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
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/wechat/wechat-configs/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
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
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/wechat/articles/${data.article_id}/publish-wechat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
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
  const token = getAccessToken();
  // Token 已由 getAccessToken() 校验
  // 直接使用 token

  const res = await fetch(`${API_BASE}/wechat/publish-wechat/status/${publishId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    const err: ApiError = await res.json();
    throw new Error(err.message || '查询微信发布状态失败');
  }

  return res.json();
}

// ============================================================
// 微博相关类型
// ============================================================

export interface WeiboConfig {
  id: string;
  name: string;
  cookie_preview?: string;
  default_suffix?: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface WeiboConfigCreate {
  name: string;
  cookie: string;
  default_suffix?: string;
}

export interface WeiboConfigUpdate {
  name?: string;
  cookie?: string;
  default_suffix?: string;
}

export interface WeiboPublishRequest {
  article_id: string;
  content?: string;
  suffix?: string;
  image_url?: string;
}

export interface WeiboPublishResponse {
  success: boolean;
  message: string;
  publish_id?: string;
  weibo_id?: string;
  weibo_url?: string;
}

export interface WeiboPublishStatus {
  publish_id: string;
  status: string;
  weibo_id?: string;
  weibo_url?: string;
  fail_reason?: string;
}

// ============================================================
// 微博配置管理
// ============================================================

export async function listWeiboConfigs(): Promise<WeiboConfig[]> {
  const res = await api.get('/weibo/weibo-configs');
  return res.data;
}

export async function createWeiboConfig(data: WeiboConfigCreate): Promise<WeiboConfig> {
  const res = await api.post('/weibo/weibo-configs', data);
  return res.data;
}

export async function updateWeiboConfig(id: string, data: WeiboConfigUpdate): Promise<WeiboConfig> {
  const res = await api.put(`/weibo/weibo-configs/${id}`, data);
  return res.data;
}

export async function deleteWeiboConfig(id: string): Promise<void> {
  await api.delete(`/weibo/weibo-configs/${id}`);
}

export async function verifyWeiboCookie(cookie: string): Promise<{ valid: boolean; user?: any; message?: string }> {
  const res = await api.post('/weibo/verify-cookie', { cookie });
  return res.data;
}

// ============================================================
// 微博发布
// ============================================================

export async function publishToWeibo(data: WeiboPublishRequest): Promise<WeiboPublishResponse> {
  const res = await api.post(`/weibo/articles/${data.article_id}/publish-weibo`, {
    content: data.content,
    suffix: data.suffix,
    image_url: data.image_url,
  });
  return res.data;
}

export async function getWeiboPublishStatus(publishId: string): Promise<WeiboPublishStatus> {
  const res = await api.get(`/weibo/publish-weibo/status/${publishId}`);
  return res.data;
}
