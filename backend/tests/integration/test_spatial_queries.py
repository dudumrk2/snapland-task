import pytest
import uuid
import datetime
from unittest.mock import AsyncMock, MagicMock
from snapland.infrastructure.db.repositories.area_repository import AreaRepository
from snapland.core.domain.area import Coordinate, Area

@pytest.fixture
def mock_session():
    session = AsyncMock()
    return session

@pytest.mark.asyncio
async def test_coords_to_polygon_text(mock_session):
    repo = AreaRepository(mock_session)
    coords = [Coordinate(lat=0.0, lng=0.0), Coordinate(lat=1.0, lng=0.0), Coordinate(lat=1.0, lng=1.0), Coordinate(lat=0.0, lng=0.0)]
    poly_text = repo._coords_to_polygon_text(coords)
    assert poly_text == "POLYGON((0.0 0.0, 0.0 1.0, 1.0 1.0, 0.0 0.0))"

@pytest.mark.asyncio
async def test_get_within_bounds_query_generation(mock_session):
    repo = AreaRepository(mock_session)
    # Just asserting that calling the method attempts to execute on session
    mock_session.execute = AsyncMock()
    # Need to mock the result properly for the complex parsing if we were to test it fully
    # Instead we just verify it doesn't crash on query generation
    
    # We will simulate empty DB response
    mock_result = MagicMock()
    mock_result.all.return_value = []
    mock_session.execute.return_value = mock_result
    
    # Needs to mock total count
    mock_count_result = MagicMock()
    mock_count_result.scalar.return_value = 0
    mock_session.execute.side_effect = [mock_count_result, mock_result]
    
    res = await repo.get_within_bounds(0.0, 0.0, 1.0, 1.0, zoom=10, limit=50)
    
    assert res.truncated is False
    assert res.areas == []
    assert mock_session.execute.call_count == 1
