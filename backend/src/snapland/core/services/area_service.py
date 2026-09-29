import uuid
import math
import datetime
import json
from typing import Sequence, Any
from snapland.core.interfaces.services import IAreaService, ISpatialService
from snapland.core.interfaces.repositories import IAreaRepository, AreaPage
from snapland.core.interfaces.cache import ICacheRepository
from snapland.core.interfaces.services import IEventPublisher
from snapland.core.domain.area import Area, AreaVersion, CreateAreaRequest, UpdateAreaRequest
from snapland.core.domain.exceptions import ConflictError

class AreaService(IAreaService):
    def __init__(
        self,
        repo: IAreaRepository,
        spatial: ISpatialService,
        cache: ICacheRepository,
        events: IEventPublisher,
        audit: Any
    ) -> None:
        self.repo = repo
        self.spatial = spatial
        self.cache = cache
        self.events = events
        self.audit = audit

    async def create_area(self, req: CreateAreaRequest, user_id: uuid.UUID) -> Area:
        val = self.spatial.validate_polygon(req.coordinates)
        if not val.valid:
            raise ValueError(f"Invalid polygon: {val.reason}")
            
        area_km2 = self.spatial.calculate_area_km2(req.coordinates)
        
        area = Area(
            id=uuid.uuid4(),
            name=req.name,
            coordinates=req.coordinates,
            area_km2=area_km2,
            version=1,
            created_by=user_id,
            last_edited_by=user_id,
            created_at=datetime.datetime.now(datetime.UTC), # handled by db
            updated_at=datetime.datetime.now(datetime.UTC)
        )
        
        created_area = await self.repo.create(area)
        await self.cache.incr("areas:epoch")
        # Domain events are fired after commit in a real impl, but we might just fire them here
        return created_area

    async def update_area(self, area_id: uuid.UUID, req: UpdateAreaRequest, user_id: uuid.UUID) -> Area:
        current_area = await self.repo.get_by_id(area_id)
        if not current_area:
            from snapland.core.domain.exceptions import NotFoundError
            raise NotFoundError("Area not found")
            
        if current_area.version != req.version:
            raise ConflictError(current_area)
            
        if req.coordinates:
            val = self.spatial.validate_polygon(req.coordinates)
            if not val.valid:
                raise ValueError(f"Invalid polygon: {val.reason}")
            area_km2 = self.spatial.calculate_area_km2(req.coordinates)
        else:
            area_km2 = current_area.area_km2
            
        updated = Area(
            id=area_id,
            name=req.name if req.name is not None else current_area.name,
            coordinates=req.coordinates if req.coordinates is not None else current_area.coordinates,
            area_km2=area_km2,
            version=req.version + 1,
            created_by=current_area.created_by,
            last_edited_by=user_id,
            created_at=current_area.created_at,
            updated_at=datetime.datetime.now(datetime.UTC)
        )
        
        res = await self.repo.update(updated, expected_version=req.version)
        if not res:
            current_area_now = await self.repo.get_by_id(area_id)
            if current_area_now:
                raise ConflictError(current_area_now)
            from snapland.core.domain.exceptions import NotFoundError
            raise NotFoundError("Area not found")
            
        await self.cache.incr("areas:epoch")
        return res

    async def delete_area(self, area_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.repo.soft_delete(area_id, user_id)
        await self.cache.incr("areas:epoch")

    async def get_areas_in_bounds(self, min_lng: float, min_lat: float, max_lng: float, max_lat: float,
                                  *, zoom: int | None = None, limit: int = 500) -> AreaPage:
        # Snap bbox outward to 0.01 degree grid
        s_min_lng = math.floor(min_lng * 100) / 100.0
        s_min_lat = math.floor(min_lat * 100) / 100.0
        s_max_lng = math.ceil(max_lng * 100) / 100.0
        s_max_lat = math.ceil(max_lat * 100) / 100.0
        
        epoch_str = await self.cache.get("areas:epoch")
        epoch = int(epoch_str) if epoch_str else 0
        
        zoom_bucket = zoom if zoom is not None else "none"
        bbox_str = f"{s_min_lng},{s_min_lat},{s_max_lng},{s_max_lat}"
        
        cache_key = f"areas:v{epoch}:z{zoom_bucket}:{bbox_str}:{limit}"
        
        cached = await self.cache.get(cache_key)
        if cached:
            import orjson
            data = orjson.loads(cached)
            areas = []
            for a in data["areas"]:
                areas.append(Area(
                    id=uuid.UUID(a["id"]),
                    name=a["name"],
                    coordinates=a["coordinates"],
                    area_km2=a["area_km2"],
                    version=a["version"],
                    created_by=uuid.UUID(a["created_by"]),
                    last_edited_by=uuid.UUID(a["last_edited_by"]),
                    created_at=a["created_at"],
                    updated_at=a["updated_at"]
                ))
            return AreaPage(areas=areas, truncated=data["truncated"])
            
        page = await self.repo.get_within_bounds(s_min_lng, s_min_lat, s_max_lng, s_max_lat, zoom=zoom, limit=limit)
        
        import orjson
        page_dict = {
            "truncated": page.truncated,
            "areas": [
                {
                    "id": str(a.id),
                    "name": a.name,
                    "coordinates": a.coordinates,
                    "area_km2": a.area_km2,
                    "version": a.version,
                    "created_by": str(a.created_by),
                    "last_edited_by": str(a.last_edited_by),
                    "created_at": a.created_at if isinstance(a.created_at, str) else a.created_at.isoformat(),
                    "updated_at": a.updated_at if isinstance(a.updated_at, str) else a.updated_at.isoformat()
                } for a in page.areas
            ]
        }
        await self.cache.set(cache_key, orjson.dumps(page_dict).decode("utf-8"), 60)
        return page

    async def get_history(self, area_id: uuid.UUID) -> Sequence[AreaVersion]:
        return await self.repo.get_version_history(area_id)
