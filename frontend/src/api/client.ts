// ─── NeerUrja API Client ──────────────────────────────────────────────────────
// Reads VITE_API_BASE_URL from environment. Default: http://127.0.0.1:8000
// All methods throw descriptive errors on non-2xx responses.

import type {
  ScenarioRequest,
  ScenarioResponse,
  Weather,
  HealthResponse,
  ValidationErrorItem,
  ApiErrorDetail,
} from '../types/api';

const BASE_URL = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000'
).replace(/\/+$/, '');

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    ...init,
  });

  if (!res.ok) {
    let detailMessage = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === 'string') {
        detailMessage = body.detail;
      } else if (Array.isArray(body?.detail)) {
        detailMessage = body.detail
          .map((err: ValidationErrorItem | string) =>
            typeof err === 'string'
              ? err
              : `${err.loc ? err.loc.join('.') + ': ' : ''}${err.msg || 'Invalid field'}`,
          )
          .join('; ');
      } else if (body?.detail && typeof body.detail === 'object') {
        const detailObj = body.detail as ApiErrorDetail;
        detailMessage = detailObj.message || detailObj.code || JSON.stringify(detailObj);
        if (detailObj.details && Array.isArray(detailObj.details) && detailObj.details.length > 0) {
          detailMessage += `: ${detailObj.details.join(', ')}`;
        }
      } else if (body?.message) {
        detailMessage = body.message;
      }
    } catch {
      /* ignore JSON parsing errors */
    }
    throw new Error(`API ${res.status}: ${detailMessage}`);
  }

  return res.json() as Promise<T>;
}

export const apiClient = {
  /** GET /health */
  health(): Promise<HealthResponse> {
    return request<HealthResponse>('/health');
  },

  /** GET /api/v1/scenarios/demo?weather=clear|cloudy */
  getDemoScenario(weather?: Weather): Promise<ScenarioRequest> {
    const query = weather ? `?weather=${encodeURIComponent(weather)}` : '';
    return request<ScenarioRequest>(`/api/v1/scenarios/demo${query}`);
  },

  /** POST /api/v1/scenarios/run */
  runScenario(payload: ScenarioRequest): Promise<ScenarioResponse> {
    return request<ScenarioResponse>('/api/v1/scenarios/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },
};
