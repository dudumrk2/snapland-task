import time
from typing import Any, Callable

from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    REGISTRY,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match


def _get_or_create_metric(metric_cls: type, name: str, documentation: str, labelnames: tuple = (), **kwargs: Any) -> Any:
    collectors = getattr(REGISTRY, "_names_to_collectors", None)
    if collectors is not None and name in collectors:
        return collectors[name]
    try:
        return metric_cls(name, documentation, labelnames, **kwargs)
    except ValueError:
        if collectors is not None and name in collectors:
            return collectors[name]
        raise


http_requests_total: Counter = _get_or_create_metric(
    Counter,
    "http_requests_total",
    "Total HTTP requests",
    ("method", "route", "status"),
)

http_request_duration_seconds: Histogram = _get_or_create_metric(
    Histogram,
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ("method", "route", "status"),
)

ws_connections_active: Gauge = _get_or_create_metric(
    Gauge,
    "ws_connections_active",
    "Number of active WebSocket connections",
)

ws_messages_total: Counter = _get_or_create_metric(
    Counter,
    "ws_messages_total",
    "Total WebSocket messages",
    ("type", "direction"),
)

ws_messages_dropped_total: Counter = _get_or_create_metric(
    Counter,
    "ws_messages_dropped_total",
    "Total dropped WebSocket messages",
    ("reason",),
)

ws_outbound_queue_depth: Histogram = _get_or_create_metric(
    Histogram,
    "ws_outbound_queue_depth",
    "WebSocket outbound queue depth",
    buckets=(0, 1, 5, 10, 25, 50, 100, 200, 256),
)

area_operations_total: Counter = _get_or_create_metric(
    Counter,
    "area_operations_total",
    "Total area operations",
    ("operation",),
)

cache_requests_total: Counter = _get_or_create_metric(
    Counter,
    "cache_requests_total",
    "Total cache requests",
    ("layer", "result"),
)

rate_limit_hits_total: Counter = _get_or_create_metric(
    Counter,
    "rate_limit_hits_total",
    "Total rate limit hits",
    ("bucket",),
)

occ_conflicts_total: Counter = _get_or_create_metric(
    Counter,
    "occ_conflicts_total",
    "Total optimistic concurrency conflicts",
)

viewport_query_duration_seconds: Histogram = _get_or_create_metric(
    Histogram,
    "viewport_query_duration_seconds",
    "Duration of viewport spatial queries in seconds",
)

db_pool_connections: Gauge = _get_or_create_metric(
    Gauge,
    "db_pool_connections",
    "Database connection pool status",
    ("state",),
)


def get_route_template(request: Request) -> str:
    """Resolves route template (e.g. /api/v1/areas/{id}) instead of raw paths to keep cardinality bounded."""
    route = request.scope.get("route")
    if route and hasattr(route, "path"):
        return route.path

    app = request.app
    if hasattr(app, "routes"):
        for r in app.routes:
            match, _ = r.matches(request.scope)
            if match == Match.FULL:
                return getattr(r, "path", request.url.path)

    # For unknown / unmatched paths
    return "unmatched"


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Exclude /metrics itself and websocket handshake
        if request.url.path == "/metrics" or request.scope.get("type") == "websocket":
            return await call_next(request)

        method = request.method
        start_time = time.monotonic()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.monotonic() - start_time
            route = get_route_template(request)
            try:
                http_requests_total.labels(method=method, route=route, status=str(status_code)).inc()
                http_request_duration_seconds.labels(method=method, route=route, status=str(status_code)).observe(duration)
            except Exception:
                pass


def update_db_pool_metrics(app: Any) -> None:
    """Updates in_use and idle DB pool connection counts if engine pool is available."""
    try:
        engine = getattr(app.state, "db_engine", None)
        if engine and hasattr(engine, "pool"):
            pool = engine.pool
            checked_out = pool.checkedout() if hasattr(pool, "checkedout") else 0
            checked_in = pool.checkedin() if hasattr(pool, "checkedin") else 0
            db_pool_connections.labels(state="in_use").set(checked_out)
            db_pool_connections.labels(state="idle").set(checked_in)
    except Exception:
        pass


def metrics_endpoint(request: Request) -> Response:
    update_db_pool_metrics(request.app)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
