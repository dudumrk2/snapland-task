from fastapi import FastAPI
from fastapi.testclient import TestClient

from snapland.middleware.metrics import (
    PrometheusMiddleware,
    area_operations_total,
    cache_requests_total,
    db_pool_connections,
    http_request_duration_seconds,
    http_requests_total,
    metrics_endpoint,
    occ_conflicts_total,
    rate_limit_hits_total,
    viewport_query_duration_seconds,
    ws_connections_active,
    ws_messages_dropped_total,
    ws_messages_total,
    ws_outbound_queue_depth,
)


def test_prometheus_metrics_declared():
    assert http_requests_total is not None
    assert http_request_duration_seconds is not None
    assert ws_connections_active is not None
    assert ws_messages_total is not None
    assert ws_messages_dropped_total is not None
    assert ws_outbound_queue_depth is not None
    assert area_operations_total is not None
    assert cache_requests_total is not None
    assert rate_limit_hits_total is not None
    assert occ_conflicts_total is not None
    assert viewport_query_duration_seconds is not None
    assert db_pool_connections is not None


def test_metrics_endpoint_and_route_template_middleware():
    app = FastAPI()
    app.add_middleware(PrometheusMiddleware)

    @app.get("/items/{item_id}")
    def get_item(item_id: str):
        return {"item_id": item_id}

    app.add_route("/metrics", metrics_endpoint, methods=["GET"])

    client = TestClient(app)
    resp = client.get("/items/123-abc")
    assert resp.status_code == 200

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics_text = metrics_resp.text

    # Route template should be /items/{item_id}, NOT the raw path /items/123-abc
    assert 'route="/items/{item_id}"' in metrics_text
    assert '123-abc' not in metrics_text
    assert "http_requests_total" in metrics_text
    assert "http_request_duration_seconds" in metrics_text
