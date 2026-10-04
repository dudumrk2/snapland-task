import datetime
import math
import uuid
from collections.abc import Sequence
from typing import Any

import structlog

from snapland.core.domain.area import (
    Area,
    AreaVersion,
    CreateAreaRequest,
    UpdateAreaRequest,
)
from snapland.core.domain.events import AreaCreated, AreaDeleted, AreaUpdated
from snapland.core.domain.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from snapland.core.interfaces.cache import ICacheRepository
from snapland.core.interfaces.repositories import AreaPage, IAreaRepository
from snapland.core.interfaces.services import (
    IAreaService,
    IEventPublisher,
    ISpatialService,
)
from snapland.middleware.metrics import area_operations_total, occ_conflicts_total

logger = structlog.get_logger(__name__)


class AreaService(IAreaService):
    def __init__(
        self,
        repo: IAreaRepository,
        spatial: ISpatialService,
        cache: ICacheRepository,
        events: IEventPublisher,
        audit: Any,
    ) -> None:
        self.repo = repo
        self.spatial = spatial
        self.cache = cache
        self.events = events
        self.audit = audit

    async def create_area(self, req: CreateAreaRequest, user_id: uuid.UUID) -> Area:
        logger.info("Creating area", name=req.name, user_id=str(user_id))
        val = self.spatial.validate_polygon(req.coordinates)
        if not val.valid:
            logger.warning("Polygon validation failed on create", reason=val.reason, user_id=str(user_id))
            raise ValidationError(f"Invalid polygon: {val.reason}")

        area_km2 = self.spatial.calculate_area_km2(req.coordinates)

        area = Area(
            id=uuid.uuid4(),
            name=req.name,
            coordinates=req.coordinates,
            area_km2=area_km2,
            version=1,
            created_by=user_id,
            last_edited_by=user_id,
            created_at=datetime.datetime.now(datetime.UTC),  # handled by db
            updated_at=datetime.datetime.now(datetime.UTC),
        )

        created_area = await self.repo.create(area)
        await self.cache.incr("areas:epoch")

        try:
            area_operations_total.labels(operation="create").inc()
        except Exception:
            pass

        created_at_dt = (
            created_area.created_at
            if isinstance(created_area.created_at, datetime.datetime)
            else datetime.datetime.fromisoformat(created_area.created_at)
        )
        try:
            await self.events.publish(
                AreaCreated(
                    area_id=created_area.id,
                    created_at=created_at_dt,
                    created_by=created_area.created_by,
                    area=created_area,
                    shape_id=req.shape_id,
                )
            )
        except Exception as e:
            logger.warning(
                "Failed to publish AreaCreated event after commit; area was saved",
                area_id=str(created_area.id),
                exc_info=e,
            )

        logger.info(
            "Area created successfully",
            area_id=str(created_area.id),
            area_km2=created_area.area_km2,
            version=created_area.version,
        )
        return created_area

    async def update_area(self, area_id: uuid.UUID, req: UpdateAreaRequest, user_id: uuid.UUID) -> Area:
        logger.info("Updating area", area_id=str(area_id), expected_version=req.version, user_id=str(user_id))
        current_area = await self.repo.get_by_id(area_id)
        if not current_area:
            logger.warning("Area not found for update", area_id=str(area_id))
            raise NotFoundError("Area not found")

        if current_area.version != req.version:
            try:
                occ_conflicts_total.inc()
            except Exception:
                pass
            logger.warning(
                "OCC conflict on update_area",
                area_id=str(area_id),
                current_version=current_area.version,
                expected_version=req.version,
            )
            raise ConflictError(current_area)

        if req.coordinates:
            val = self.spatial.validate_polygon(req.coordinates)
            if not val.valid:
                logger.warning("Polygon validation failed on update", reason=val.reason, area_id=str(area_id))
                raise ValidationError(f"Invalid polygon: {val.reason}")
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
            updated_at=datetime.datetime.now(datetime.UTC),
        )

        res = await self.repo.update(updated, expected_version=req.version)
        if not res:
            current_area_now = await self.repo.get_by_id(area_id)
            if current_area_now:
                try:
                    occ_conflicts_total.inc()
                except Exception:
                    pass
                logger.warning(
                    "OCC conflict during repo update",
                    area_id=str(area_id),
                    current_version=current_area_now.version,
                )
                raise ConflictError(current_area_now)
            logger.warning("Area not found after update attempt", area_id=str(area_id))
            raise NotFoundError("Area not found")

        await self.cache.incr("areas:epoch")

        try:
            area_operations_total.labels(operation="update").inc()
        except Exception:
            pass

        updated_at_dt = (
            res.updated_at
            if isinstance(res.updated_at, datetime.datetime)
            else datetime.datetime.fromisoformat(res.updated_at)
        )
        try:
            await self.events.publish(
                AreaUpdated(
                    area_id=res.id,
                    version=res.version,
                    updated_at=updated_at_dt,
                    updated_by=user_id,
                    area=res,
                )
            )
        except Exception as e:
            logger.warning(
                "Failed to publish AreaUpdated event after commit; area was saved",
                area_id=str(res.id),
                exc_info=e,
            )

        logger.info("Area updated successfully", area_id=str(res.id), version=res.version, area_km2=res.area_km2)
        return res

    async def delete_area(self, area_id: uuid.UUID, user_id: uuid.UUID) -> None:
        logger.info("Deleting area", area_id=str(area_id), user_id=str(user_id))
        deleted = await self.repo.soft_delete(area_id, user_id)
        if not deleted:
            raise NotFoundError(f"Area {area_id} not found")
        await self.cache.incr("areas:epoch")

        try:
            area_operations_total.labels(operation="delete").inc()
        except Exception:
            pass

        try:
            await self.events.publish(
                AreaDeleted(
                    area_id=area_id,
                    deleted_at=datetime.datetime.now(datetime.UTC),
                    deleted_by=user_id,
                )
            )
        except Exception as e:
            logger.warning(
                "Failed to publish AreaDeleted event after commit; area was soft-deleted",
                area_id=str(area_id),
                exc_info=e,
            )
        logger.info("Area deleted successfully", area_id=str(area_id))

    async def get_area(self, area_id: uuid.UUID) -> Area:
        logger.debug("Retrieving area", area_id=str(area_id))
        area = await self.repo.get_by_id(area_id)
        if not area:
            logger.warning("Area not found", area_id=str(area_id))
            raise NotFoundError("Area not found")
        return area

    async def get_areas_in_bounds(
        self,
        min_lng: float,
        min_lat: float,
        max_lng: float,
        max_lat: float,
        *,
        zoom: int | None = None,
        limit: int = 500,
    ) -> AreaPage:
        logger.debug(
            "Querying viewport areas",
            min_lng=min_lng,
            min_lat=min_lat,
            max_lng=max_lng,
            max_lat=max_lat,
            zoom=zoom,
            limit=limit,
        )
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
            try:
                import orjson

                data = orjson.loads(cached)
                if isinstance(data, dict) and "areas" in data:
                    areas = []
                    for a in data["areas"]:
                        areas.append(
                            Area(
                                id=uuid.UUID(a["id"]),
                                name=a["name"],
                                coordinates=a["coordinates"],
                                area_km2=a["area_km2"],
                                version=a["version"],
                                created_by=uuid.UUID(a["created_by"]),
                                last_edited_by=uuid.UUID(a["last_edited_by"]),
                                created_at=a["created_at"],
                                updated_at=a["updated_at"],
                            )
                        )
                    return AreaPage(areas=areas, truncated=data.get("truncated", False))
            except Exception:
                pass

        page = await self.repo.get_within_bounds(s_min_lng, s_min_lat, s_max_lng, s_max_lat, zoom=zoom, limit=limit)

        try:
            page_areas = getattr(page, "areas", []) or []
            if not isinstance(page_areas, (list, tuple)):
                page_areas = []
            import orjson

            page_dict = {
                "truncated": bool(getattr(page, "truncated", False)),
                "areas": [
                    {
                        "id": str(getattr(a, "id", "")),
                        "name": str(getattr(a, "name", "")),
                        "coordinates": [
                            c.model_dump() if hasattr(c, "model_dump") else c
                            for c in getattr(a, "coordinates", [])
                        ],
                        "area_km2": float(getattr(a, "area_km2", 0.0)),
                        "version": int(getattr(a, "version", 1)),
                        "created_by": str(getattr(a, "created_by", "")),
                        "last_edited_by": str(getattr(a, "last_edited_by", "")),
                        "created_at": (
                            a.created_at
                            if isinstance(getattr(a, "created_at", None), str)
                            else (a.created_at.isoformat() if hasattr(a, "created_at") else "")
                        ),
                        "updated_at": (
                            a.updated_at
                            if isinstance(getattr(a, "updated_at", None), str)
                            else (a.updated_at.isoformat() if hasattr(a, "updated_at") else "")
                        ),
                    }
                    for a in page_areas
                ],
            }
            await self.cache.set(cache_key, orjson.dumps(page_dict).decode("utf-8"), 60)
        except Exception:
            pass
        return page

    async def get_history(self, area_id: uuid.UUID) -> Sequence[AreaVersion]:
        logger.debug("Retrieving area version history", area_id=str(area_id))
        return await self.repo.get_version_history(area_id)
