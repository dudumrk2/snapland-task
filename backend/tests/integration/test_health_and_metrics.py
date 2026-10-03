import pytest
from fastapi.testclient import TestClient

from main import app


def test_health_live():
    with TestClient(app) as client:
        resp = client.get("/health/live")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


def test_health_ready():
    with TestClient(app) as client:
        resp = client.get("/health/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "ok", "degraded")
        assert data["database"] == "ok"
        assert data["redis"] == "ok"
        assert data["instance_id"] != ""
        assert data["version"] == "1.0.0"


def test_health_db_spatial_index():
    with TestClient(app) as client:
        resp = client.get("/health/db")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["index_used"] == "areas_geom_gist"
        assert "areas_geom_gist" in data["plan"]


def test_health_db_missing_spatial_index_returns_500(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock
    from snapland.infrastructure.db import session as db_session_module

    # Mock engine connection returning a Seq Scan plan without areas_geom_gist
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(return_value=MagicMock(fetchall=lambda: [("Seq Scan on areas (cost=0.00..10.00)",)]))
    mock_conn.begin = MagicMock()
    mock_conn.begin.return_value.__aenter__ = AsyncMock()
    mock_conn.begin.return_value.__aexit__ = AsyncMock()

    mock_engine = MagicMock()
    mock_engine.connect = MagicMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock()
    mock_engine.dispose = AsyncMock()

    monkeypatch.setattr(db_session_module, "engine", mock_engine)
    app.state.db_engine = mock_engine

    with TestClient(app) as client:
        resp = client.get("/health/db")
        assert resp.status_code == 500
        data = resp.json()
        assert data["status"] == "error"
        assert data["message"] == "Spatial index not used"
        assert "Seq Scan on areas" in data["plan"]

    # Restore engine
    delattr(app.state, "db_engine")


def test_metrics_endpoint():
    with TestClient(app) as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        text = resp.text
        # Check all required metric names from HLD §16
        expected_metrics = [
            "http_requests_total",
            "http_request_duration_seconds",
            "ws_connections_active",
            "ws_messages_total",
            "ws_messages_dropped_total",
            "ws_outbound_queue_depth",
            "area_operations_total",
            "cache_requests_total",
            "rate_limit_hits_total",
            "occ_conflicts_total",
            "viewport_query_duration_seconds",
            "db_pool_connections",
        ]
        for m in expected_metrics:
            assert m in text, f"Metric {m} missing from /metrics output"
