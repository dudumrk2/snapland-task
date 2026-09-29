from sqlalchemy import text
import json
import uuid
from uuid import UUID
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import select, update, insert, text, func, cast
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_Intersects, ST_MakeEnvelope, ST_SimplifyPreserveTopology, ST_AsGeoJSON, ST_Area, ST_GeomFromText
from geoalchemy2.types import Geography

from snapland.core.domain.area import Area, AreaVersion, Coordinate
from snapland.core.interfaces.repositories import IAreaRepository, AreaPage
from snapland.infrastructure.db.models import AreaModel, AreaVersionModel, AuditLogModel
from snapland.infrastructure.db.repositories.base import BaseRepository

class AreaRepository(BaseRepository[AreaModel], IAreaRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, AreaModel)

    def _coords_to_polygon_text(self, coords: Sequence[Coordinate]) -> str:
        if not coords:
            return "POLYGON EMPTY"
        points = [f"{c.lng} {c.lat}" for c in coords]
        if points[0] != points[-1]:
            points.append(points[0])
        return f"POLYGON(({', '.join(points)}))"

    def _geojson_to_coords(self, geojson_str: str) -> Sequence[Coordinate]:
        if not geojson_str:
            return []
        data = json.loads(geojson_str)
        if data.get("type") == "Polygon" and data.get("coordinates"):
            ring = data["coordinates"][0]
            # Domain coordinates is open ring? We'll just return it as is or drop the last if closed.
            if len(ring) > 0 and ring[0] == ring[-1]:
                ring = ring[:-1]
            return [Coordinate(lat=lat, lng=lng) for lng, lat in ring]
        return []

    async def get_by_id(self, area_id: UUID) -> Area | None: # type: ignore[override]
        stmt = (
            select(AreaModel, func.ST_AsGeoJSON(AreaModel.geom).label("geojson"))
            .where(AreaModel.id == area_id)
            .where(AreaModel.deleted_at.is_(None))
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return None
        model, geojson = row
        return Area(
            id=model.id,
            name=model.name,
            coordinates=list(self._geojson_to_coords(geojson)),
            area_km2=model.area_km2,
            version=model.version,
            created_by=model.created_by,
            last_edited_by=model.last_edited_by,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    async def get_within_bounds(
        self, min_lng: float, min_lat: float, max_lng: float, max_lat: float,
        *, zoom: int | None = None, limit: int = 500,
    ) -> AreaPage:
        # Simplification tolerance based on zoom.
        tolerance = 0.0
        if zoom is not None and zoom < 16:
            # Approximate calculation: roughly 360 / (256 * 2^zoom)
            tolerance = 360.0 / (256 * (2 ** zoom))

        geom_expr = AreaModel.geom
        if tolerance > 0:
            geom_expr = ST_SimplifyPreserveTopology(AreaModel.geom, tolerance) # type: ignore

        stmt = (
            select(AreaModel, func.ST_AsGeoJSON(geom_expr).label("geojson"))
            .where(AreaModel.deleted_at.is_(None))
            .where(ST_Intersects(AreaModel.geom, ST_MakeEnvelope(min_lng, min_lat, max_lng, max_lat, 4326)))
            .limit(limit + 1)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        truncated = len(rows) > limit
        if truncated:
            rows = rows[:limit]

        areas = []
        for model, geojson in rows:
            areas.append(Area(
                id=model.id,
                name=model.name,
                coordinates=list(self._geojson_to_coords(geojson)),
                area_km2=model.area_km2,
                version=model.version,
                created_by=model.created_by,
                last_edited_by=model.last_edited_by,
                created_at=model.created_at,
                updated_at=model.updated_at,
            ))
        return AreaPage(areas=areas, truncated=truncated)

    async def get_version_history(self, area_id: UUID) -> Sequence[AreaVersion]:
        stmt = (
            select(AreaVersionModel)
            .where(AreaVersionModel.area_id == area_id)
            .order_by(AreaVersionModel.version_number.desc())
        )
        result = await self.session.execute(stmt)
        models = result.scalars().all()
        versions = []
        for m in models:
            versions.append(AreaVersion(
                version_number=m.version_number,
                edited_by=m.edited_by,
                change_type=m.change_type,
                area_km2=m.area_km2,
                created_at=m.created_at,
                diff=m.diff
            ))
        return versions

    async def create(self, area: Area) -> Area:
        polygon_wkt = self._coords_to_polygon_text(area.coordinates)
        geom_val = func.ST_GeomFromText(polygon_wkt, 4326)
        
        stmt = (
            insert(AreaModel)
            .values(
                id=area.id,
                name=area.name,
                geom=geom_val,
                area_km2=func.ST_Area(cast(geom_val, Geography)) / 1000000.0,
                created_by=area.created_by,
                last_edited_by=area.last_edited_by,
                version=area.version,
                created_at=datetime.fromisoformat(area.created_at) if isinstance(area.created_at, str) else area.created_at,
                updated_at=datetime.fromisoformat(area.updated_at) if isinstance(area.updated_at, str) else area.updated_at,
            )
            .returning(AreaModel.area_km2)
        )
        result = await self.session.execute(stmt)
        computed_area_km2 = result.scalar()
        
        version_stmt = insert(AreaVersionModel).values(
            id=uuid.uuid4(),
            area_id=area.id,
            area_km2=computed_area_km2,
            edited_by=area.created_by,
            version_number=area.version,
            change_type="create",
            created_at=datetime.fromisoformat(area.created_at) if isinstance(area.created_at, str) else area.created_at,
            diff={}
        )
        await self.session.execute(version_stmt)
        audit_stmt = insert(AuditLogModel).values(
            id=uuid.uuid4(),
            user_id=area.created_by,
            action="create",
            resource_type="area",
            resource_id=area.id,
            details={},
            created_at=datetime.fromisoformat(area.created_at) if isinstance(area.created_at, str) else area.created_at
        )
        await self.session.execute(audit_stmt)
        
        await self.session.flush()
        
        return Area(
            id=area.id,
            name=area.name,
            coordinates=area.coordinates,
            area_km2=computed_area_km2 or 0.0,
            version=area.version,
            created_by=area.created_by,
            last_edited_by=area.last_edited_by,
            created_at=area.created_at,
            updated_at=area.updated_at
        )

    async def update(self, area: Area, expected_version: int) -> Area | None:
        polygon_wkt = self._coords_to_polygon_text(area.coordinates)
        
        query = text("""
            WITH updated AS (
                UPDATE areas
                SET name = :name,
                    geom = ST_GeomFromText(:geom, 4326),
                    area_km2 = ST_Area(ST_GeomFromText(:geom, 4326)::geography) / 1000000.0,
                    last_edited_by = :last_edited_by,
                    version = :version,
                    updated_at = :updated_at
                WHERE id = :id AND version = :expected_version AND deleted_at IS NULL
                RETURNING id, name, ST_AsGeoJSON(geom) as geojson, area_km2, version, created_by, last_edited_by, created_at, updated_at
            )
            SELECT *, true as is_updated FROM updated
            UNION ALL
            SELECT id, name, ST_AsGeoJSON(geom) as geojson, area_km2, version, created_by, last_edited_by, created_at, updated_at, false as is_updated
            FROM areas
            WHERE id = :id AND NOT EXISTS (SELECT 1 FROM updated)
        """)
        
        result = await self.session.execute(
            query, 
            {
                "name": area.name,
                "geom": polygon_wkt,
                "last_edited_by": area.last_edited_by,
                "version": area.version,
                "updated_at": area.updated_at,
                "id": area.id,
                "expected_version": expected_version
            }
        )
        row = result.first()
        
        if not row:
            return None # Deleted or doesn't exist
            
        ret_area = Area(
            id=row.id,
            name=row.name,
            coordinates=list(self._geojson_to_coords(row.geojson)),
            area_km2=row.area_km2,
            version=row.version,
            created_by=row.created_by,
            last_edited_by=row.last_edited_by,
            created_at=row.created_at,
            updated_at=row.updated_at
        )
        
        if not row.is_updated:
            from snapland.core.domain.exceptions import ConflictError
            raise ConflictError(ret_area)
            
        # Write area version
        version_stmt = insert(AreaVersionModel).values(
            id=uuid.uuid4(),
            area_id=area.id,
            area_km2=row.area_km2,
            edited_by=area.last_edited_by,
            version_number=area.version,
            change_type="update",
            created_at=datetime.fromisoformat(area.updated_at) if isinstance(area.updated_at, str) else area.updated_at,
            diff={}
        )
        await self.session.execute(version_stmt)
        audit_stmt = insert(AuditLogModel).values(
            id=uuid.uuid4(),
            user_id=area.last_edited_by,
            action="update",
            resource_type="area",
            resource_id=area.id,
            details={},
            created_at=datetime.fromisoformat(area.updated_at) if isinstance(area.updated_at, str) else area.updated_at
        )
        await self.session.execute(audit_stmt)
        await self.session.flush()
        
        return ret_area


    async def soft_delete(self, area_id: UUID, deleted_by: UUID) -> bool:
        now = datetime.now(timezone.utc)
        stmt = (
            update(AreaModel)
            .where(AreaModel.id == area_id)
            .where(AreaModel.deleted_at.is_(None))
            .values(
                deleted_at=now,
                last_edited_by=deleted_by,
                updated_at=now
            )
            .returning(AreaModel.version, AreaModel.area_km2, AreaModel.geom)
        )
        result = await self.session.execute(stmt)
        row = result.first()
        if not row:
            return False
            
        version, area_km2, geom = row
        
        version_stmt = insert(AreaVersionModel).values(
            id=uuid.uuid4(),
            area_id=area_id,
            area_km2=area_km2,
            edited_by=deleted_by,
            version_number=version + 1,
            change_type="delete",
            created_at=now,
            diff={}
        )
        await self.session.execute(version_stmt)
        audit_stmt = insert(AuditLogModel).values(
            id=uuid.uuid4(),
            user_id=deleted_by,
            action="delete",
            resource_type="area",
            resource_id=area_id,
            details={},
            created_at=now
        )
        await self.session.execute(audit_stmt)
        
        await self.session.flush()
        return True
