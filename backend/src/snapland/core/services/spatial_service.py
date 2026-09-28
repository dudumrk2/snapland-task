import math
from typing import Sequence, Any
import shapely.geometry  # type: ignore
from pyproj import Geod

from snapland.core.interfaces.services import PolygonValidation, ISpatialService
from snapland.core.domain.area import Coordinate

class SpatialService(ISpatialService):
    def __init__(self) -> None:
        self.geod = Geod(ellps="WGS84")

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
        poly_coords = self._deduplicate_close(coordinates)
        if len(poly_coords) < 4:
            return 0.0
        
        lons = [c.lng for c in poly_coords]
        lats = [c.lat for c in poly_coords]
        
        poly_area, _ = self.geod.polygon_area_perimeter(lons, lats)
        return float(abs(poly_area) / 1_000_000.0)

    def validate_polygon(self, coordinates: Sequence[Coordinate]) -> PolygonValidation:
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
            
        if len(poly_coords) - 1 > 1000:
            return PolygonValidation(valid=False, reason="TOO_MANY_VERTICES")
            
        lons = [c.lng for c in poly_coords]
        lats = [c.lat for c in poly_coords]
        
        polygon = shapely.geometry.Polygon(zip(lons, lats))
        if not polygon.is_valid:
            return PolygonValidation(valid=False, reason="SELF_INTERSECTION")
            
        area_km2 = self.calculate_area_km2(coordinates)
        
        if area_km2 < 0.000001:
            return PolygonValidation(valid=False, reason="AREA_TOO_SMALL")
            
        if area_km2 > 25000.0:
            return PolygonValidation(valid=False, reason="AREA_TOO_LARGE")
            
        return PolygonValidation(valid=True)

    def to_geojson_polygon(self, coordinates: Sequence[Coordinate]) -> dict[str, Any]:
        poly_coords = self._deduplicate_close(coordinates)
        return {
            "type": "Polygon",
            "coordinates": [[[c.lng, c.lat] for c in poly_coords]]
        }

    def simplify_tolerance_deg(self, zoom: int | None) -> float:
        if zoom is None or zoom >= 16:
            return 0.0
        return float(360.0 / (256.0 * (2 ** zoom)))
