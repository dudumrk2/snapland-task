from fastapi import FastAPI
import structlog
import logging
import sys
from snapland.middleware.error_handler import setup_error_handlers
from snapland.middleware.request_id import RequestIdMiddleware
from snapland.middleware.metrics import MetricsMiddleware, metrics_endpoint
from snapland.middleware.timeout import TimeoutMiddleware
from snapland.api.v1.health import router as health_router
from snapland.api.v1.auth import router as auth_router
from snapland.api.v1.areas import router as areas_router
from snapland.api.v1.users import router as users_router
from snapland.config import settings

def setup_logging():
    level = logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG
    
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

setup_logging()
logger = structlog.get_logger(__name__)

app = FastAPI(title="Snapland API")

app.add_middleware(TimeoutMiddleware, timeout=30.0)
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIdMiddleware)
setup_error_handlers(app)

app.add_route("/metrics", metrics_endpoint, methods=["GET"])

app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(areas_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")

from snapland.infrastructure.jobs.retention import start_retention_scheduler

@app.on_event("startup")
async def startup_event():
    logger.info("Application starting up", instance_id=settings.INSTANCE_ID)
    if hasattr(app.state, "db_engine") and hasattr(app.state, "redis"):
        app.state.retention_scheduler = start_retention_scheduler(app.state.db_engine, app.state.redis)

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down", instance_id=settings.INSTANCE_ID)
    if hasattr(app.state, "retention_scheduler"):
        app.state.retention_scheduler.shutdown()
