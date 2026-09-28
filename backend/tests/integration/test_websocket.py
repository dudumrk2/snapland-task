import pytest
from snapland.api.websocket.manager import WebSocketManager

@pytest.mark.asyncio
async def test_manager_coalesce():
    manager = WebSocketManager()
    # Test coalescing logic here
    assert manager is not None

