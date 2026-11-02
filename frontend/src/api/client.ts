import { ApiError } from './errors';
import type {
  ApiErrorBody,
  GeocodeResponse,
  HeatmapRequest,
  HeatmapResponse,
  PlanRequest,
  PlanResponse,
} from './types';

const BASE = import.meta.env.VITE_API_BASE ?? '';

async function parseError(res: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> | null = null;
  try {
    body = (await res.json()) as Partial<ApiErrorBody>;
  } catch {
    // Non-JSON error page (e.g. a proxy 502 while the service is waking up).
  }
  const err = body?.error;
  return new ApiError({
    status: res.status,
    code: err?.code ?? (res.status >= 500 ? 'routing_unavailable' : 'validation_error'),
    message: err?.message ?? `The server responded with HTTP ${res.status}.`,
    retryAfterS: err?.retry_after_s,
    fields: err?.fields,
  });
}

async function request<T>(path: string, init: RequestInit & { signal: AbortSignal }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(BASE + path, init);
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new ApiError({ status: 0, code: 'network_error', message: 'Could not reach the server.' });
  }
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

const post = <T>(path: string, body: unknown, signal: AbortSignal) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  });

export const api = {
  plan: (body: PlanRequest, signal: AbortSignal) => post<PlanResponse>('/api/plan', body, signal),
  heatmap: (body: HeatmapRequest, signal: AbortSignal) => post<HeatmapResponse>('/api/heatmap', body, signal),
  geocode: (q: string, signal: AbortSignal) =>
    request<GeocodeResponse>(`/api/geocode?q=${encodeURIComponent(q)}`, { signal }),
  health: (signal: AbortSignal) => request<{ status: string }>('/api/health/', { signal }),
};
