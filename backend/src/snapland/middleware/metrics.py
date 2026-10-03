from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time

# HTTP metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "route", "status"]
)

# WS metrics
ws_connections_active = Gauge("ws_connections_active", "Active WebSocket connections")
ws_messages_total = Counter("ws_messages_total", "Total WebSocket messages", ["direction", "type"])
ws_messages_dropped_total = Counter("ws_messages_dropped_total", "Dropped WebSocket messages", ["reason"])
ws_outbound_queue_depth = Histogram("ws_outbound_queue_depth", "WebSocket outbound queue depth")

# Application metrics
area_operations_total = Counter("area_operations_total", "Area operations", ["operation"])
cache_requests_total = Counter("cache_requests_total", "Cache requests", ["layer", "result"])
rate_limit_hits_total = Counter("rate_limit_hits_total", "Rate limit hits", ["bucket"])
occ_conflicts_total = Counter("occ_conflicts_total", "OCC conflicts")
viewport_query_duration_seconds = Histogram("viewport_query_duration_seconds", "Viewport query duration")

# DB metrics
db_pool_connections = Gauge("db_pool_connections", "DB pool connections", ["state"])


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        route = request.url.path
        # Use router match for route template instead of raw path to avoid cardinality explosion
        if request.scope.get("route"):
            route = request.scope["route"].path
            
        start_time = time.perf_counter()
        
        try:
            response = await call_next(request)
            status = str(response.status_code)
        except Exception:
            status = "500"
            raise
        finally:
            duration = time.perf_counter() - start_time
            http_requests_total.labels(method=method, route=route, status=status).inc()
            http_request_duration_seconds.labels(method=method, route=route, status=status).observe(duration)
            
        return response

def metrics_endpoint(request: Request):
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
