import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import type {
  Area,
  AreasPage,
  AreaVersion,
  BoundingBox,
  CreateAreaRequest,
  UpdateAreaRequest,
} from '@snapland/shared-types';
import { IAreaApi, ConflictError } from '../interfaces/IAreaApi';
import type { IAuthApi } from '../interfaces/IAuthApi';
import { realAuthApi } from './authApi';
import { useAuthStore } from '../../store/authStore';

export function normalizeArea(raw: any): Area {
  if (!raw) {
    return {
      id: '',
      name: '',
      coordinates: [],
      areaKm2: 0,
      version: 1,
      createdBy: '',
      lastEditedBy: '',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };
  }
  return {
    id: String(raw.id ?? ''),
    name: String(raw.name ?? ''),
    coordinates: Array.isArray(raw.coordinates) ? raw.coordinates : [],
    areaKm2:
      typeof raw.areaKm2 === 'number'
        ? raw.areaKm2
        : typeof raw.area_km2 === 'number'
        ? raw.area_km2
        : 0,
    version: typeof raw.version === 'number' ? raw.version : 1,
    createdBy: String(raw.createdBy ?? raw.created_by ?? ''),
    lastEditedBy: String(raw.lastEditedBy ?? raw.last_edited_by ?? ''),
    createdAt: String(raw.createdAt ?? raw.created_at ?? ''),
    updatedAt: String(raw.updatedAt ?? raw.updated_at ?? ''),
  };
}

export function normalizeAreaVersion(raw: any): AreaVersion {
  return {
    versionNumber: raw.versionNumber ?? raw.version_number ?? 1,
    editedBy: String(raw.editedBy ?? raw.edited_by ?? ''),
    changeType: raw.changeType ?? raw.change_type ?? 'update',
    areaKm2:
      typeof raw.areaKm2 === 'number'
        ? raw.areaKm2
        : typeof raw.area_km2 === 'number'
        ? raw.area_km2
        : 0,
    createdAt: String(raw.createdAt ?? raw.created_at ?? ''),
    diff: raw.diff ?? {},
  };
}

export class AreaApi implements IAreaApi {
  private client: AxiosInstance;
  private authApi: IAuthApi;

  constructor(authApi: IAuthApi = realAuthApi, baseURL: string = '/api/v1/areas') {
    this.authApi = authApi;
    this.client = axios.create({
      baseURL,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Request interceptor to attach Bearer token from memory store
    this.client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
      const token = useAuthStore.getState().accessToken;
      if (token && !config.headers.Authorization) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Response interceptor for 401 (silent refresh), 409 (OCC Conflict), and 429 (Rate limit)
    this.client.interceptors.response.use(
      (response) => response,
      async (error: AxiosError<any>) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };

        // 1. On 401: call authApi.refresh() once, update token, and retry the request
        if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
          originalRequest._retry = true;
          try {
            const tokenResponse = await this.authApi.refresh();
            const user = useAuthStore.getState().user;
            if (user) {
              useAuthStore.getState().setSession(user, tokenResponse.accessToken);
            }
            originalRequest.headers.Authorization = `Bearer ${tokenResponse.accessToken}`;
            return this.client(originalRequest);
          } catch (refreshError) {
            useAuthStore.getState().clearSession();
            return Promise.reject(refreshError);
          }
        }

        // 2. On 409 (Conflict): parse response body `details` and throw ConflictError
        if (error.response?.status === 409) {
          const body = error.response.data;
          const details = body?.details || {};
          const rawCurrent = details.current_area || details.currentArea;
          const currentArea = normalizeArea(rawCurrent);
          const currentVersion = details.current_version ?? details.currentVersion ?? currentArea.version;
          const message = body?.message || 'Area was modified by another user';

          return Promise.reject(new ConflictError(message, currentArea, currentVersion));
        }

        // 3. On 429: parse Retry-After header and surface notification without auto-retrying
        if (error.response?.status === 429) {
          const retryHeader = error.response.headers['retry-after'];
          const details = error.response.data?.details;
          let retryAfterMs = details?.retryAfterMs;
          if (!retryAfterMs && retryHeader) {
            const sec = parseInt(retryHeader, 10);
            if (!isNaN(sec)) retryAfterMs = sec * 1000;
          }
          const seconds = retryAfterMs ? Math.ceil(retryAfterMs / 1000) : 60;
          const message = `Rate limit reached. Please wait ${seconds}s before attempting this action.`;

          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('snapland:toast', { detail: { message } })
            );
          }
          return Promise.reject(error);
        }

        return Promise.reject(error);
      }
    );
  }

  async getAreasInBounds(bounds: BoundingBox, zoom: number): Promise<AreasPage> {
    const boundsStr = `${bounds.minLng},${bounds.minLat},${bounds.maxLng},${bounds.maxLat}`;
    const res = await this.client.get<{ areas: any[]; truncated: boolean }>('', {
      params: {
        bounds: boundsStr,
        zoom,
        limit: 500,
      },
    });

    return {
      areas: (res.data.areas || []).map(normalizeArea),
      truncated: Boolean(res.data.truncated),
    };
  }

  async getAreaById(id: string): Promise<Area> {
    const res = await this.client.get(`/${id}`);
    return normalizeArea(res.data);
  }

  async createArea(req: CreateAreaRequest): Promise<Area> {
    const res = await this.client.post('', {
      name: req.name.trim(),
      coordinates: req.coordinates,
    });
    return normalizeArea(res.data);
  }

  async updateArea(id: string, req: UpdateAreaRequest): Promise<Area> {
    const res = await this.client.put(`/${id}`, {
      version: req.version,
      name: req.name !== undefined ? req.name.trim() : undefined,
      coordinates: req.coordinates,
    });
    return normalizeArea(res.data);
  }

  async deleteArea(id: string): Promise<void> {
    await this.client.delete(`/${id}`);
  }

  async getAreaHistory(id: string): Promise<AreaVersion[]> {
    const res = await this.client.get<any[]>(`/${id}/history`);
    return (res.data || []).map(normalizeAreaVersion);
  }
}

export const realAreaApi = new AreaApi();
