// Axios instance + request/response interceptors for the FNAI API.
//
// Auth state lives in the zustand store; we read it through a getter so we
// can update tokens without re-creating the instance.

import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from 'axios';
import { useAuthStore } from '@/stores/auth';
import type { ApiError, TokenPair } from '@/types/api';

export const api: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '/api/v1',
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
});

// Inject the access token on every request.
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  // ⚠️ 用 getState() 而不是 hook 形式，因为 axios 拦截器不是 React 组件
  // 这种"在 React 外部访问 store"是 zustand 的常见模式
  const state = useAuthStore.getState();
  const token = state.accessToken;
  if (token) {
    config.headers.set?.('Authorization', `Bearer ${token}`);
  }

  // 同时把当前激活的租户 ID 塞到 X-Tenant-Id header
  // 这样后端业务接口可以读到当前在哪个租户下工作
  // （虽然 JWT payload 里也有 active_tenant_id，但 header 更直观，
  //   方便中间件、日志、审计）
  const tenantId = state.activeTenantId;
  if (tenantId) {
    config.headers.set?.('X-Tenant-Id', tenantId);
  }

  return config;
});

// Translate FastAPI HTTPException details into typed ApiError.
function toApiError(err: AxiosError): ApiError {
  const data = err.response?.data as { code?: string; message?: string } | undefined;
  if (data && typeof data === 'object' && 'code' in data && 'message' in data) {
    return { code: data.code ?? 'unknown', message: data.message ?? 'Unknown error' };
  }
  return { code: 'network_error', message: err.message || 'Network error' };
}

// One in-flight refresh promise shared across concurrent 401 responses.
let refreshInFlight: Promise<string | null> | null = null;

async function tryRefresh(): Promise<string | null> {
  const { refreshToken, setAccessToken, clear } = useAuthStore.getState();
  if (!refreshToken) return null;
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const fresh = axios.create({ baseURL: api.defaults.baseURL });
        const r = await fresh.post<TokenPair>('/auth/refresh', { refresh_token: refreshToken });
        setAccessToken(r.data.access_token);
        return r.data.access_token;
      } catch {
        clear();
        return null;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

api.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (err: AxiosError) => {
    const original = err.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (err.response?.status === 401 && original && !original._retry) {
      original._retry = true;
      const newToken = await tryRefresh();
      if (newToken) {
        original.headers.set?.('Authorization', `Bearer ${newToken}`);
        return api.request(original);
      }
    }
    return Promise.reject(toApiError(err));
  },
);
