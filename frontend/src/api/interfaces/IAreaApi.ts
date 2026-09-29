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

  constructor(message: string, currentArea: Area) {
    super(message);
    this.name = 'ConflictError';
    this.currentArea = currentArea;
    Object.setPrototypeOf(this, ConflictError.prototype);
  }
}

export interface IAreaApi {
  getAreasInBounds(bounds: BoundingBox, zoom: number): Promise<AreasPage>;
  getAreaById(id: string): Promise<Area>;
  createArea(req: CreateAreaRequest): Promise<Area>;
  updateArea(id: string, req: UpdateAreaRequest): Promise<Area>; // rejects with ConflictError on 409
  deleteArea(id: string): Promise<void>;
  getAreaHistory(id: string): Promise<AreaVersion[]>;
}
