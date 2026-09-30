import type {
  Area,
  AreasPage,
  AreaVersion,
  CreateAreaRequest,
  UpdateAreaRequest,
  BoundingBox,
} from '@snapland/shared-types';
import { IAreaApi, ConflictError } from '../interfaces/IAreaApi';
import { calculatePolygonAreaKm2 } from '../../utils/areaCalculation';
import { isPointInBounds } from '../../utils/geoUtils';

export const INITIAL_AREAS: Area[] = [
  {
    id: 'area-1',
    name: 'Tel Aviv Port District',
    coordinates: [
      { lat: 32.0965, lng: 34.7712 },
      { lat: 32.1012, lng: 34.7754 },
      { lat: 32.0988, lng: 34.7815 },
      { lat: 32.0935, lng: 34.7782 },
    ],
    areaKm2: 0.54,
    version: 1,
    createdBy: 'system',
    lastEditedBy: 'system',
    createdAt: new Date(Date.now() - 3600000).toISOString(),
    updatedAt: new Date(Date.now() - 3600000).toISOString(),
  },
  {
    id: 'area-2',
    name: 'Jerusalem Old City Basin',
    coordinates: [
      { lat: 31.7812, lng: 35.2285 },
      { lat: 31.7825, lng: 35.2372 },
      { lat: 31.7745, lng: 35.2391 },
      { lat: 31.7732, lng: 35.2301 },
    ],
    areaKm2: 0.88,
    version: 1,
    createdBy: 'system',
    lastEditedBy: 'system',
    createdAt: new Date(Date.now() - 7200000).toISOString(),
    updatedAt: new Date(Date.now() - 7200000).toISOString(),
  },
];

export class MockAreaApi implements IAreaApi {
  private areas: Map<string, Area> = new Map();
  private history: Map<string, AreaVersion[]> = new Map();
  private simulatedLatencyMs = 60;

  constructor(initialAreas: Area[] = []) {
    initialAreas.forEach((area) => {
      this.areas.set(area.id, { ...area });
      this.history.set(area.id, [
        {
          versionNumber: area.version,
          editedBy: area.lastEditedBy,
          changeType: 'create',
          areaKm2: area.areaKm2,
          createdAt: area.createdAt,
          diff: { initial: true },
        },
      ]);
    });
  }

  private async delay(): Promise<void> {
    if (this.simulatedLatencyMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, this.simulatedLatencyMs));
    }
  }

  async getAreasInBounds(bounds: BoundingBox, _zoom: number): Promise<AreasPage> {
    await this.delay();
    const result: Area[] = [];

    for (const area of this.areas.values()) {
      // Area is included if any of its coordinates falls in bounds or simple overlap
      const hasPoint = area.coordinates.some((coord) =>
        isPointInBounds(coord, bounds)
      );
      if (hasPoint) {
        result.push({ ...area });
      }
    }

    return {
      areas: result.length > 0 ? result : Array.from(this.areas.values()),
      truncated: false,
    };
  }

  async getAreaById(id: string): Promise<Area> {
    await this.delay();
    const area = this.areas.get(id);
    if (!area) {
      throw new Error(`Area not found: ${id}`);
    }
    return { ...area };
  }

  async createArea(req: CreateAreaRequest): Promise<Area> {
    await this.delay();
    const id = `area-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
    const areaKm2 = calculatePolygonAreaKm2(req.coordinates);
    const now = new Date().toISOString();

    const newArea: Area = {
      id,
      name: req.name.trim(),
      coordinates: req.coordinates,
      areaKm2: Number(areaKm2.toFixed(3)),
      version: 1,
      createdBy: 'currentUser',
      lastEditedBy: 'currentUser',
      createdAt: now,
      updatedAt: now,
    };

    this.areas.set(id, newArea);
    this.history.set(id, [
      {
        versionNumber: 1,
        editedBy: 'currentUser',
        changeType: 'create',
        areaKm2: newArea.areaKm2,
        createdAt: now,
        diff: { name: newArea.name },
      },
    ]);

    return { ...newArea };
  }

  async updateArea(id: string, req: UpdateAreaRequest): Promise<Area> {
    await this.delay();
    const current = this.areas.get(id);
    if (!current) {
      throw new Error(`Area not found: ${id}`);
    }

    // Enforce Optimistic Concurrency Control (OCC)
    if (req.version !== current.version) {
      throw new ConflictError(
        `Version conflict: Expected version ${req.version} but current is ${current.version}`,
        { ...current }
      );
    }

    const nextVersion = current.version + 1;
    const now = new Date().toISOString();
    const coordinates = req.coordinates ?? current.coordinates;
    const areaKm2 = req.coordinates
      ? Number(calculatePolygonAreaKm2(coordinates).toFixed(3))
      : current.areaKm2;

    const updatedArea: Area = {
      ...current,
      name: req.name?.trim() ?? current.name,
      coordinates,
      areaKm2,
      version: nextVersion,
      lastEditedBy: 'currentUser',
      updatedAt: now,
    };

    this.areas.set(id, updatedArea);

    const historyList = this.history.get(id) || [];
    historyList.push({
      versionNumber: nextVersion,
      editedBy: 'currentUser',
      changeType: 'update',
      areaKm2: updatedArea.areaKm2,
      createdAt: now,
      diff: {
        nameChanged: req.name !== undefined && req.name !== current.name,
        geometryChanged: req.coordinates !== undefined,
      },
    });
    this.history.set(id, historyList);

    return { ...updatedArea };
  }

  async deleteArea(id: string): Promise<void> {
    await this.delay();
    const current = this.areas.get(id);
    if (!current) {
      throw new Error(`Area not found: ${id}`);
    }
    this.areas.delete(id);
  }

  async getAreaHistory(id: string): Promise<AreaVersion[]> {
    await this.delay();
    const list = this.history.get(id);
    if (!list) {
      return [];
    }
    return [...list];
  }
}

export const mockAreaApi = new MockAreaApi();
