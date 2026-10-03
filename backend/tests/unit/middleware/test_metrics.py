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


def test_all_declared_metrics_in_metrics_output():
    app = FastAPI()
    app.add_route("/metrics", metrics_endpoint, methods=["GET"])

    client = TestClient(app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    text = resp.text

    expected = [
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
    for m in expected:
        assert m in text, f"Expected metric '{m}' to appear in /metrics output"


def test_metrics_unmatched_route_template():
    app = FastAPI()
    app.add_middleware(PrometheusMiddleware)
    app.add_route("/metrics", metrics_endpoint, methods=["GET"])

    client = TestClient(app)
    # Request a non-existent path
    resp = client.get("/non-existent/random-uuid-12345")
    assert resp.status_code == 404

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200
    metrics_text = metrics_resp.text

    # Route label must be "unmatched" rather than the raw 404 path
    assert 'route="unmatched"' in metrics_text
    assert 'random-uuid-12345' not in metrics_text


def test_ws_metrics_manipulation():
    # Test gauges and counters direct observation/increment
    initial_conn = ws_connections_active._value.get()
    ws_connections_active.inc()
    assert ws_connections_active._value.get() == initial_conn + 1
    ws_connections_active.dec()
    assert ws_connections_active._value.get() == initial_conn

    ws_messages_total.labels(type="CURSOR_MOVE", direction="inbound").inc()
    ws_messages_dropped_total.labels(reason="queue_full").inc()
    ws_outbound_queue_depth.observe(12)
    area_operations_total.labels(operation="create").inc()
    occ_conflicts_total.inc()
    viewport_query_duration_seconds.observe(0.042)
