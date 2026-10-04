import math
from collections.abc import Sequence
from typing import Any

import shapely.geometry  # type: ignore
import structlog
from pyproj import Geod

from snapland.core.domain.area import Coordinate
from snapland.core.interfaces.services import ISpatialService, PolygonValidation

logger = structlog.get_logger(__name__)


class SpatialService(ISpatialService):
    def __init__(
        self,
        max_area_km2: float | None = None,
        max_polygon_vertices: int | None = None,
    ) -> None:
        from snapland.config import settings

        self.geod = Geod(ellps="WGS84")
        self.max_area_km2 = (
            max_area_km2 if max_area_km2 is not None else settings.MAX_AREA_KM2
        )
        self.max_polygon_vertices = (
            max_polygon_vertices
            if max_polygon_vertices is not None
            else settings.MAX_POLYGON_VERTICES
        )

    def _deduplicate_close(self, coordinates: Sequence[Coordinate]) -> list[Coordinate]:
        if not coordinates:
            return []
        res = [coordinates[0]]
        for i in range(1, len(coordinates)):
            if coordinates[i].lat != res[-1].lat or coordinates[i].lng != res[-1].lng:
                res.append(coordinates[i])
        if len(res) > 0 and (res[-1].lat != res[0].lat or res[-1].lng != res[0].lng):
            res.append(res[0])
        return res

    def calculate_area_km2(self, coordinates: Sequence[Coordinate]) -> float:
        logger.debug("Calculating area km2 for coordinates", count=len(coordinates))
        poly_coords = self._deduplicate_close(coordinates)
        if len(poly_coords) < 4:
            return 0.0

        lons = [c.lng for c in poly_coords]
        lats = [c.lat for c in poly_coords]

        poly_area, _ = self.geod.polygon_area_perimeter(lons, lats)
        return float(abs(poly_area) / 1_000_000.0)

    def validate_polygon(self, coordinates: Sequence[Coordinate]) -> PolygonValidation:
        logger.debug("Validating polygon coordinates", count=len(coordinates))
        for c in coordinates:
            if math.isnan(c.lat) or math.isinf(c.lat) or math.isnan(c.lng) or math.isinf(c.lng):
                return PolygonValidation(valid=False, reason="INVALID_COORDINATE")
            if not (-90.0 <= c.lat <= 90.0):
                return PolygonValidation(valid=False, reason="INVALID_LATITUDE")
            if not (-180.0 <= c.lng <= 180.0):
                return PolygonValidation(valid=False, reason="INVALID_LONGITUDE")

        poly_coords = self._deduplicate_close(coordinates)

        if len(poly_coords) - 1 < 3:
            return PolygonValidation(valid=False, reason="TOO_FEW_VERTICES")

        if len(poly_coords) - 1 > self.max_polygon_vertices:
            return PolygonValidation(valid=False, reason="TOO_MANY_VERTICES")

        lons = [c.lng for c in poly_coords]
        lats = [c.lat for c in poly_coords]

        polygon = shapely.geometry.Polygon(zip(lons, lats))
        if not polygon.is_valid:
            return PolygonValidation(valid=False, reason="SELF_INTERSECTION")

        area_km2 = self.calculate_area_km2(coordinates)

        if area_km2 < 0.000001:
            return PolygonValidation(valid=False, reason="AREA_TOO_SMALL")

        if area_km2 > self.max_area_km2:
            return PolygonValidation(valid=False, reason="AREA_TOO_LARGE")

        return PolygonValidation(valid=True)

    def to_geojson_polygon(self, coordinates: Sequence[Coordinate]) -> dict[str, Any]:
        poly_coords = self._deduplicate_close(coordinates)
        return {
            "type": "Polygon",
            "coordinates": [[[c.lng, c.lat] for c in poly_coords]],
        }

    def simplify_tolerance_deg(self, zoom: int | None) -> float:
        if zoom is None or zoom >= 16:
            return 0.0
        return float(360.0 / (256.0 * (2 ** zoom)))
