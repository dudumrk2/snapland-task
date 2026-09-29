
import pytest

from snapland.core.domain.area import Coordinate
from snapland.core.services.spatial_service import SpatialService


@pytest.fixture
def spatial_service():
    return SpatialService()

def test_calculate_area_km2(spatial_service):
    # A simple square
    coords = [
        Coordinate(lat=0.0, lng=0.0),
        Coordinate(lat=0.1, lng=0.0),
        Coordinate(lat=0.1, lng=0.1),
        Coordinate(lat=0.0, lng=0.1),
        Coordinate(lat=0.0, lng=0.0)
    ]
    area = spatial_service.calculate_area_km2(coords)
    # 0.1 degree at equator is approx 11.1km. 11.1 * 11.1 = ~123 km^2
    assert 120 < area < 125

def test_validate_polygon_valid(spatial_service):
    coords = [
        Coordinate(lat=0.0, lng=0.0),
        Coordinate(lat=0.1, lng=0.0),
        Coordinate(lat=0.1, lng=0.1),
        Coordinate(lat=0.0, lng=0.1),
        Coordinate(lat=0.0, lng=0.0)
    ]
    res = spatial_service.validate_polygon(coords)
    assert res.valid is True
    assert res.reason is None

def test_validate_polygon_invalid_coordinate(spatial_service):
    coords = [
        Coordinate(lat=float('inf'), lng=0.0),
        Coordinate(lat=0.1, lng=0.0),
        Coordinate(lat=0.1, lng=0.1),
        Coordinate(lat=0.0, lng=0.0)
    ]
    res = spatial_service.validate_polygon(coords)
    assert res.valid is False
    assert res.reason == "INVALID_COORDINATE"

def test_validate_polygon_too_few_vertices(spatial_service):
    coords = [
        Coordinate(lat=0.0, lng=0.0),
        Coordinate(lat=0.1, lng=0.0),
        Coordinate(lat=0.0, lng=0.0)
    ]
    res = spatial_service.validate_polygon(coords)
    assert res.valid is False
    assert res.reason == "TOO_FEW_VERTICES"

def test_validate_polygon_self_intersection(spatial_service):
    # Bowtie polygon
    coords = [
        Coordinate(lat=0.0, lng=0.0),
        Coordinate(lat=0.1, lng=0.1),
        Coordinate(lat=0.1, lng=0.0),
        Coordinate(lat=0.0, lng=0.1),
        Coordinate(lat=0.0, lng=0.0)
    ]
    res = spatial_service.validate_polygon(coords)
    assert res.valid is False
    assert res.reason == "SELF_INTERSECTION"

def test_validate_polygon_area_too_small(spatial_service):
    coords = [
        Coordinate(lat=0.0, lng=0.0),
        Coordinate(lat=0.0000001, lng=0.0),
        Coordinate(lat=0.0000001, lng=0.0000001),
        Coordinate(lat=0.0, lng=0.0000001),
        Coordinate(lat=0.0, lng=0.0)
    ]
    res = spatial_service.validate_polygon(coords)
    assert res.valid is False
    assert res.reason == "AREA_TOO_SMALL"

def test_to_geojson_polygon(spatial_service):
    coords = [
        Coordinate(lat=0.0, lng=1.0),
        Coordinate(lat=1.0, lng=1.0),
        Coordinate(lat=1.0, lng=2.0),
        Coordinate(lat=0.0, lng=1.0)
    ]
    res = spatial_service.to_geojson_polygon(coords)
    assert res["type"] == "Polygon"
    assert len(res["coordinates"]) == 1
    assert res["coordinates"][0] == [[1.0, 0.0], [1.0, 1.0], [2.0, 1.0], [1.0, 0.0]]

def test_simplify_tolerance_deg(spatial_service):
    assert spatial_service.simplify_tolerance_deg(16) == 0.0
    assert spatial_service.simplify_tolerance_deg(None) == 0.0
    assert spatial_service.simplify_tolerance_deg(10) > 0.0
