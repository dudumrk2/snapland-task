import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { useAuthStore } from '../../store/authStore';
import { ConflictError } from '../interfaces/IAreaApi';
import { showToast } from '../../utils/toastService';
import type { Area } from '@snapland/shared-types';

export function mapServerAreaToArea(raw: unknown): Area {
  const item = raw as Record<string, unknown> | null | undefined;
  if (!item) {
    throw new Error('Invalid area data: payload is null or undefined');
  }

  const coordinates = Array.isArray(item.coordinates)
    ? (item.coordinates as Area['coordinates'])
    : [];

  const areaKm2 = typeof item.areaKm2 === 'number'
    ? item.areaKm2
    : typeof item.area_km2 === 'number'
    ? item.area_km2
    : 0;

  const version = typeof item.version === 'number' ? item.version : 1;
  const createdBy = typeof item.createdBy === 'string'
    ? item.createdBy
    : typeof item.created_by === 'string'
    ? item.created_by
    : '';

  const lastEditedBy = typeof item.lastEditedBy === 'string'
    ? item.lastEditedBy
    : typeof item.last_edited_by === 'string'
    ? item.last_edited_by
    : '';

  const createdAt = typeof item.createdAt === 'string'
    ? item.createdAt
    : typeof item.created_at === 'string'
    ? item.created_at
    : new Date().toISOString();

  const updatedAt = typeof item.updatedAt === 'string'
    ? item.updatedAt
    : typeof item.updated_at === 'string'
    ? item.updated_at
    : new Date().toISOString();

  return {
    id: String(item.id || ''),
    name: String(item.name || ''),
    coordinates,
    areaKm2,
    version,
    createdBy,
    lastEditedBy,
    createdAt,
    updatedAt,
  };
}

const baseURL = import.meta.env.VITE_API_BASE_URL || '';

export const apiClient = axios.create({
  baseURL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

let refreshPromise: Promise<string | null> | null = null;
let refreshHandler: (() => Promise<string | null>) | null = null;

export function registerRefreshHandler(handler: () => Promise<string | null>): void {
  refreshHandler = handler;
}

// Request interceptor: inject Authorization header from authStore
apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const accessToken = useAuthStore.getState().accessToken;
  if (accessToken && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

interface RetryRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
}

// Response interceptor: 401 refresh/retry, 409 ConflictError, 429 Retry-After toast
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryRequestConfig | undefined;
    const status = error.response?.status;

    // 409 Conflict: throw ConflictError carrying details.current_version and details.current_area
    if (status === 409) {
      const data = error.response?.data as
        | { details?: { current_version?: number; current_area?: unknown } }
        | undefined;
      const details = data?.details;
      const currentArea = details?.current_area
        ? mapServerAreaToArea(details.current_area)
        : ({
            id: '',
            name: '',
            coordinates: [],
            areaKm2: 0,
            version: details?.current_version ?? 1,
            createdBy: '',
            lastEditedBy: '',
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
          } as Area);

      throw new ConflictError(
        'Area was modified by another user',
        currentArea,
        details?.current_version
      );
    }

    // 429 Rate Limited: honour Retry-After header, surface toast, do not retry automatically
    if (status === 429) {
      const headers = error.response?.headers;
      const retryAfterHeader =
        headers?.['retry-after'] || headers?.['Retry-After'];
      const retryAfterSec = retryAfterHeader ? Number(retryAfterHeader) : null;
      const msg = retryAfterSec
        ? `Rate limited. Please retry in ${retryAfterSec}s.`
        : 'Too many requests. Please wait a moment.';
      showToast(msg);
      return Promise.reject(error);
    }

    // 401 Unauthorized: refresh token once, retry once, then redirect to login
    if (status === 401 && originalRequest && !originalRequest._retry) {
      const url = originalRequest.url || '';
      // Do not attempt refresh on auth endpoints (login, register, refresh)
      if (url.includes('/auth/refresh') || url.includes('/auth/login') || url.includes('/auth/register')) {
        return Promise.reject(error);
      }

      originalRequest._retry = true;

      try {
        if (!refreshPromise) {
          const handler = refreshHandler
            ? refreshHandler()
            : Promise.reject(new Error('No refresh handler registered'));
          refreshPromise = handler.finally(() => {
            refreshPromise = null;
          });
        }

        const newAccessToken = await refreshPromise;

        if (newAccessToken) {
          originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          return apiClient(originalRequest);
        }
      } catch (refreshErr) {
        useAuthStore.getState().clearSession();
        if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
        return Promise.reject(refreshErr);
      }

      useAuthStore.getState().clearSession();
      if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }

    return Promise.reject(error);
  }
);
