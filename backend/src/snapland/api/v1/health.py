from datetime import datetime, timezone
import typing

import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from snapland.config import settings

log = structlog.get_logger(__name__)
router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    db: str = "ok"
    database: str = "ok"
    redis: str = "ok"
    instance_id: str = ""
    timestamp: str = ""
    version: str = "1.0.0"
    background_tasks: typing.Optional[dict[str, bool]] = None


@router.get("/health/live")
async def health_live() -> typing.Any:
    return {"status": "ok"}


@router.get("/health/ready", response_model=HealthResponse)
@router.get("/health", response_model=HealthResponse, include_in_schema=False)
async def health_ready(request: Request, response: Response) -> typing.Any:
    db_status = "ok"
    redis_status = "ok"
    status_code = 200
    overall_status = "healthy"

    try:
        db_engine = getattr(request.app.state, "db_engine", None)
        if not db_engine:
            from snapland.infrastructure.db.session import engine
            db_engine = engine

        from sqlalchemy import text
        async with db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as e:
        log.error("DB health check failed", error=str(e))
        db_status = "down"
        overall_status = "unhealthy"
        status_code = 503

    try:
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client:
            await redis_client.ping()
    except Exception as e:
        log.error("Redis health check failed", error=str(e))
        redis_status = "down"
        if overall_status == "healthy":
            overall_status = "degraded"
        status_code = 503

    bg_tasks = getattr(request.app.state, "bg_tasks_status", None)
    if bg_tasks and any(not is_healthy for is_healthy in bg_tasks.values()):
        if overall_status == "healthy":
            overall_status = "degraded"

    response.status_code = status_code
    return HealthResponse(
        status=overall_status,
        db=db_status,
        database=db_status,
        redis=redis_status,
        instance_id=settings.INSTANCE_ID,
        timestamp=datetime.now(timezone.utc).isoformat(),
        version="1.0.0",
        background_tasks=bg_tasks,
    )


@router.get("/health/db")
async def health_db(request: Request) -> typing.Any:
    """Verifies that the spatial index is used for viewport queries."""
    db_engine = getattr(request.app.state, "db_engine", None)
    if not db_engine:
        from snapland.infrastructure.db.session import engine
        db_engine = engine

    from sqlalchemy import text
    try:
        async with db_engine.connect() as conn:
            async with conn.begin():
                # Set enable_seqscan = off locally in transaction to force index usage if possible
                await conn.execute(text("SET LOCAL enable_seqscan = off;"))

                # Run EXPLAIN on the viewport query
                query = text("""
                    EXPLAIN SELECT areas.id, ST_AsGeoJSON(areas.geom) AS geojson 
                    FROM areas 
                    WHERE areas.deleted_at IS NULL 
                      AND ST_Intersects(areas.geom, ST_MakeEnvelope(34.0, 31.0, 35.0, 32.0, 4326)) 
                    LIMIT 501
                """)
                result = await conn.execute(query)
                plan = "\n".join([row[0] for row in result.fetchall()])

                if "areas_geom_gist" in plan:
                    return {"status": "ok", "index_used": "areas_geom_gist", "plan": plan}
                else:
                    return JSONResponse(status_code=500, content={"status": "error", "message": "Spatial index not used", "plan": plan})
    except Exception as e:
        log.error("DB index check failed", error=str(e))
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})
