/**
 * API 基础客户端（基于 fetch，无需 axios 依赖）
 * 后端根路径：/api/v1（通过 vite proxy 转发到 http://localhost:8000）
 */

const BASE = '/api/v1';

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = 10000,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        'X-Request-ID': crypto.randomUUID(),
        ...(init.headers ?? {}),
      },
    });

    clearTimeout(timer);

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const detail = body?.detail ?? body;
      const code = detail?.error ?? 'API_ERROR';
      const message = detail?.message ?? `HTTP ${res.status}`;
      throw new ApiError(res.status, code, message);
    }

    return res.json() as Promise<T>;
  } catch (err) {
    clearTimeout(timer);
    if (err instanceof ApiError) throw err;
    if ((err as Error).name === 'AbortError') {
      throw new ApiError(504, 'TIMEOUT', '请求超时，请稍后重试');
    }
    throw new ApiError(0, 'NETWORK_ERROR', '网络连接异常，请检查网络');
  }
}

export const apiGet = <T>(path: string, timeoutMs?: number) =>
  request<T>(path, { method: 'GET' }, timeoutMs);

export const apiPost = <T>(path: string, body: unknown, timeoutMs?: number) =>
  request<T>(
    path,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    },
    timeoutMs,
  );

export const apiDelete = <T>(path: string) =>
  request<T>(path, { method: 'DELETE' });

/** 文件上传（multipart/form-data，不设 Content-Type 让浏览器自动加 boundary）*/
export const apiUpload = <T>(
  path: string,
  formData: FormData,
  timeoutMs = 30000,
) =>
  request<T>(
    path,
    {
      method: 'POST',
      body: formData,
    },
    timeoutMs,
  );
