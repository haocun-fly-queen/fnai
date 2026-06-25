// Auth API calls — thin wrappers around the FastAPI endpoints.

import { api } from '@/lib/api';
import type { CurrentUserResponse, TokenPair } from '@/types/api';

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  tenant_name: string;
  tenant_slug?: string;
}

export interface RegisterResponseHeaders {
  accessToken: string;
  refreshToken: string;
}

export async function login(payload: LoginPayload): Promise<TokenPair> {
  const { data } = await api.post<TokenPair>('/auth/login', payload);
  return data;
}

export async function register(payload: RegisterPayload): Promise<RegisterResponseHeaders> {
  // Backend returns tokens in headers (X-Access-Token, X-Refresh-Token)
  // and the user payload in the body. axios exposes response headers on
  // the AxiosResponse, but we don't have it here — call via the raw client.
  const res = await api.post<CurrentUserResponse>('/auth/register', payload, {
    transformResponse: (d) => d,
  });
  const accessToken = res.headers['x-access-token'];
  const refreshToken = res.headers['x-refresh-token'];
  if (!accessToken || !refreshToken) {
    throw { code: 'register_no_tokens', message: 'Server did not return tokens' };
  }
  return { accessToken, refreshToken };
}

export async function fetchMe(): Promise<CurrentUserResponse> {
  const { data } = await api.get<CurrentUserResponse>('/auth/me');
  return data;
}

export async function refreshTokens(refreshToken: string): Promise<TokenPair> {
  const { data } = await api.post<TokenPair>('/auth/refresh', { refresh_token: refreshToken });
  return data;
}
