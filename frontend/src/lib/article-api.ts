// 文章 HTTP API 客户端（阶段 4）。
// 复用 lib/api.ts 的 axios 实例（自动带 token + 401 刷新）。

import { api } from './api';

// ---- 类型 ----

export interface ArticleSummary {
  id: string;
  title: string;
  topic: string;
  template_code: string;
  knowledge_base_id: string | null;
  status: string;
  word_count: number;
  created_at: string;
  updated_at: string;
}

export interface ArticleDetail extends ArticleSummary {
  content: string;
  outline: { title: string; sections: { heading: string; key_points: string[] }[] } | null;
  seo_meta: { meta_title?: string; meta_description?: string; keywords?: string[] } | null;
  error_message: string | null;
}

export interface ArticleVersion {
  id: string;
  article_id: string;
  version_no: number;
  title: string;
  content: string;
  note: string | null;
  created_at: string;
}

export interface TemplateSummary {
  code: string;
  name: string;
  description: string;
  default_word_count: number;
}

// ---- API ----

// 列文章
export async function listArticles(): Promise<{ items: ArticleSummary[]; total: number }> {
  const r = await api.get('/articles');
  return r.data;
}

// 创建文章
export async function createArticle(payload: {
  title: string;
  topic: string;
  template_code: string;
  knowledge_base_id?: string;
}): Promise<ArticleDetail> {
  const r = await api.post('/articles', payload);
  return r.data;
}

// 文章详情
export async function getArticle(articleId: string): Promise<ArticleDetail> {
  const r = await api.get(`/articles/${articleId}`);
  return r.data;
}

// 编辑保存
export async function updateArticle(
  articleId: string,
  payload: { title?: string; content?: string; seo_meta?: Record<string, unknown> },
): Promise<ArticleDetail> {
  const r = await api.patch(`/articles/${articleId}`, payload);
  return r.data;
}

// 删除
export async function deleteArticle(articleId: string): Promise<void> {
  await api.delete(`/articles/${articleId}`);
}

// 触发生成（同步，30-90s，超时设 3 分钟）
export async function generateArticle(
  articleId: string,
  targetWordCount?: number,
): Promise<ArticleDetail> {
  const r = await api.post(
    `/articles/${articleId}/generate`,
    { target_word_count: targetWordCount },
    { timeout: 180_000 }, // 3 分钟，四阶段 LLM 调用需要更长时间
  );
  return r.data;
}

// 列模板
export async function listTemplates(): Promise<{ items: TemplateSummary[]; total: number }> {
  const r = await api.get('/templates');
  return r.data;
}

// 列版本
export async function listVersions(
  articleId: string,
): Promise<{ items: ArticleVersion[]; total: number }> {
  const r = await api.get(`/articles/${articleId}/versions`);
  return r.data;
}

// 打版本快照
export async function saveVersion(
  articleId: string,
  note?: string,
): Promise<ArticleVersion> {
  const r = await api.post(`/articles/${articleId}/versions`, { note: note || null });
  return r.data;
}
