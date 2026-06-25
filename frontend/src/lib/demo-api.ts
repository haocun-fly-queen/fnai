// Demo API calls — 包装 4 个测试端点 + token 解码工具。
//
// 本文件是"开发测试桩"，生产前会删掉。

import { api } from './api';

export type DemoResult = {
  ok: boolean;
  status: number;
  body: unknown;
};

/** 调一个 demo 端点，把状态码 + body 一起返回。 */
export async function callDemo(path: string, method: 'GET' | 'POST' = 'POST'): Promise<DemoResult> {
  try {
    const resp = await api.request({
      url: path,
      method,
    });
    return { ok: true, status: resp.status, body: resp.data };
  } catch (err) {
    // axios 拦截器已经标准化成 ApiError-like 对象
    const e = err as { code?: string; message?: string; status?: number };
    return {
      ok: false,
      status: e.status ?? 0,
      body: { code: e.code ?? 'unknown', message: e.message ?? 'Unknown error' },
    };
  }
}

/**
 * 解码 JWT payload 部分（中间那段 base64）。
 * ⚠️ 不验签——只看 payload 显示"我是谁"。
 * 这是给开发面板用的便利函数。
 */
export function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;
    const payload = parts[1];
    // base64url → base64 → 解码
    if (!payload) return null;
    const padded = payload.replace(/-/g, '+').replace(/_/g, '/');
    const json = atob(padded + '='.repeat((4 - (padded.length % 4)) % 4));
    return JSON.parse(json);
  } catch {
    return null;
  }
}
