import { Coordinate } from './geo';

export interface Area {
  id: string;
  name: string;
  coordinates: Coordinate[];      // open ring; server closes it when building GeoJSON
  areaKm2: number;                // authoritative, from PostGIS
  version: number;
  createdBy: string;
  lastEditedBy: string;
  createdAt: string;
  updatedAt: string;
}
export interface AreasPage { areas: Area[]; truncated: boolean; }
export interface AreaVersion {
  versionNumber: number; editedBy: string; changeType: 'create' | 'update' | 'delete';
  areaKm2: number; createdAt: string; diff: Record<string, unknown>;
}
export interface CreateAreaRequest { name: string; coordinates: Coordinate[]; }
export interface UpdateAreaRequest { name?: string; coordinates?: Coordinate[]; version: number; }
