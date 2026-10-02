import type {
  Area,
  AreasPage,
  AreaVersion,
  CreateAreaRequest,
  UpdateAreaRequest,
  BoundingBox,
} from '@snapland/shared-types';
import { IAreaApi } from '../interfaces/IAreaApi';
import { apiClient, mapServerAreaToArea } from './client';

export function mapServerVersionToVersion(raw: unknown): AreaVersion {
  const item = raw as Record<string, unknown> | null | undefined;
  if (!item) {
    throw new Error('Invalid version data');
  }

  const versionNumber = typeof item.versionNumber === 'number'
    ? item.versionNumber
    : typeof item.version_number === 'number'
    ? item.version_number
    : 1;

  const editedBy = typeof item.editedBy === 'string'
    ? item.editedBy
    : typeof item.edited_by === 'string'
    ? item.edited_by
    : '';

  const changeType = (typeof item.changeType === 'string'
    ? item.changeType
    : typeof item.change_type === 'string'
    ? item.change_type
    : 'update') as AreaVersion['changeType'];

  const areaKm2 = typeof item.areaKm2 === 'number'
    ? item.areaKm2
    : typeof item.area_km2 === 'number'
    ? item.area_km2
    : 0;

  const createdAt = typeof item.createdAt === 'string'
    ? item.createdAt
    : typeof item.created_at === 'string'
    ? item.created_at
    : new Date().toISOString();

  const diff = (item.diff && typeof item.diff === 'object'
    ? (item.diff as Record<string, unknown>)
    : {}) as Record<string, unknown>;

  return {
    versionNumber,
    editedBy,
    changeType,
    areaKm2,
    createdAt,
    diff,
  };
}

export interface CreateAreaRequestWithShapeId extends CreateAreaRequest {
  shapeId?: string;
}

export class RealAreaApi implements IAreaApi {
  async getAreasInBounds(
    bounds: BoundingBox,
    zoom: number
  ): Promise<AreasPage> {
    const boundsStr = `${bounds.minLng},${bounds.minLat},${bounds.maxLng},${bounds.maxLat}`;
    const response = await apiClient.get<{
      areas: unknown[];
      truncated: boolean;
    }>('/api/v1/areas', {
      params: {
        bounds: boundsStr,
        zoom,
        limit: 500,
      },
    });

    const areas = (response.data.areas || []).map(mapServerAreaToArea);
    return {
      areas,
      truncated: Boolean(response.data.truncated),
    };
  }

  async getAreaById(id: string): Promise<Area> {
    const response = await apiClient.get<unknown>(`/api/v1/areas/${id}`);
    return mapServerAreaToArea(response.data);
  }

  async createArea(req: CreateAreaRequestWithShapeId): Promise<Area> {
    const payload: {
      name: string;
      coordinates: typeof req.coordinates;
      shape_id?: string;
    } = {
      name: req.name,
      coordinates: req.coordinates,
    };
    if (req.shapeId) {
      payload.shape_id = req.shapeId;
    }

    const response = await apiClient.post<unknown>('/api/v1/areas', payload);
    return mapServerAreaToArea(response.data);
  }

  async updateArea(id: string, req: UpdateAreaRequest): Promise<Area> {
    const payload: {
      version: number;
      name?: string;
      coordinates?: typeof req.coordinates;
    } = {
      version: req.version,
    };
    if (req.name !== undefined) payload.name = req.name;
    if (req.coordinates !== undefined) payload.coordinates = req.coordinates;

    const response = await apiClient.put<unknown>(
      `/api/v1/areas/${id}`,
      payload
    );
    return mapServerAreaToArea(response.data);
  }

  async deleteArea(id: string): Promise<void> {
    await apiClient.delete(`/api/v1/areas/${id}`);
  }

  async getAreaHistory(id: string): Promise<AreaVersion[]> {
    const response = await apiClient.get<unknown[]>(
      `/api/v1/areas/${id}/history`
    );
    return (response.data || []).map(mapServerVersionToVersion);
  }
}

export const realAreaApi = new RealAreaApi();
