// 知识库 HTTP API 客户端（Step 5）。
// 复用 lib/api.ts 的 axios 实例（自动带 token + 401 刷新）。

import { api } from './api';

export interface KnowledgeBase {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  document_count: number;
  created_at: string;
}

export interface DocumentItem {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string; // pending | processing | ready | failed
  error_message: string | null;
  chunk_count: number;
  created_at: string;
}

export interface SearchResultItem {
  chunk_id: string;
  document_id: string;
  filename: string;
  chunk_index: number;
  content: string;
  score: number;
}

// 列出当前租户的知识库
export async function listKbs(): Promise<{ items: KnowledgeBase[]; total: number }> {
  const r = await api.get('/knowledge');
  return r.data;
}

// 创建知识库
export async function createKb(name: string, slug: string, description?: string): Promise<KnowledgeBase> {
  const r = await api.post('/knowledge', { name, slug, description: description || null });
  return r.data;
}

// 列出某 KB 下的文档（含状态统计）
export async function listDocuments(
  kbId: string,
): Promise<{ items: DocumentItem[]; total: number; pending_count: number; ready_count: number; failed_count: number }> {
  const r = await api.get(`/knowledge/${kbId}/documents`);
  return r.data;
}

// 上传文档（multipart）
export async function uploadDocument(kbId: string, file: File): Promise<DocumentItem> {
  const form = new FormData();
  form.append('file', file);
  const r = await api.post(`/knowledge/${kbId}/documents`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return r.data;
}

// 语义检索
export async function searchKb(
  kbId: string,
  query: string,
  topK = 5,
): Promise<{ query: string; items: SearchResultItem[]; total: number }> {
  const r = await api.post(`/knowledge/${kbId}/search`, { query, top_k: topK });
  return r.data;
}
