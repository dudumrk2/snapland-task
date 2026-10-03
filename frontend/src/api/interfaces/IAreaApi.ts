import type {
  Area,
  AreasPage,
  AreaVersion,
  CreateAreaRequest,
  UpdateAreaRequest,
  BoundingBox,
} from '@snapland/shared-types';

export class ConflictError extends Error {
  readonly currentArea: Area;
  readonly currentVersion?: number;

  constructor(message: string, currentArea: Area, currentVersion?: number) {
    super(message);
    this.name = 'ConflictError';
    this.currentArea = currentArea;
    this.currentVersion = currentVersion ?? currentArea.version;
    Object.setPrototypeOf(this, ConflictError.prototype);
  }
}

export interface CreateAreaRequestWithShapeId extends CreateAreaRequest {
  shapeId?: string;
}

export interface IAreaApi {
  getAreasInBounds(bounds: BoundingBox, zoom: number): Promise<AreasPage>;
  getAreaById(id: string): Promise<Area>;
  createArea(req: CreateAreaRequestWithShapeId): Promise<Area>;
  updateArea(id: string, req: UpdateAreaRequest): Promise<Area>; // rejects with ConflictError on 409
  deleteArea(id: string): Promise<void>;
  getAreaHistory(id: string): Promise<AreaVersion[]>;
}
