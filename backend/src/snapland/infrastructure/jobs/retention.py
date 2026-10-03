from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from snapland.infrastructure.db.models import (
    AreaModel,
    AreaVersionModel,
    AuditLogModel,
    SessionModel,
)

logger = structlog.get_logger(__name__)

RETENTION_LOCK_KEY = "snapland:job:retention:lock"
RETENTION_LOCK_TTL = 3600  # 1 hour TTL


async def run_retention_job(
    session_factory: async_sessionmaker,
    redis_client: Any,
    instance_id: str,
) -> dict[str, int]:
    """Runs data retention tasks guarded by Redis distributed SET NX lock.

    Tasks:
    1. Purge soft-deleted areas older than 90 days.
    2. Prune area_versions older than 1 year for deleted areas.
    3. Delete audit_logs older than 1 year.
    4. Delete expired/revoked sessions older than 30 days.
    """
    # Attempt to acquire distributed lock
    try:
        acquired = await redis_client.set(RETENTION_LOCK_KEY, instance_id, nx=True, ex=RETENTION_LOCK_TTL)
    except Exception as e:
        logger.error("Failed to acquire Redis lock for retention job", error=str(e))
        return {}

    if not acquired:
        logger.info("Retention job skipped: lock already held by another instance", instance_id=instance_id)
        return {}

    logger.info("Starting data retention job", instance_id=instance_id)
    now = datetime.now(timezone.utc)
    cutoff_90d = now - timedelta(days=90)
    cutoff_1y = now - timedelta(days=365)
    cutoff_30d = now - timedelta(days=30)

    summary: dict[str, int] = {
        "purged_soft_deleted_areas": 0,
        "pruned_area_versions": 0,
        "deleted_audit_logs": 0,
        "deleted_sessions": 0,
    }

    try:
        async with session_factory() as session:
            async with session.begin():
                # 1. Prune area_versions older than 1 year for deleted areas
                subquery_deleted_areas = select(AreaModel.id).where(AreaModel.deleted_at.is_not(None))
                stmt_versions = (
                    delete(AreaVersionModel)
                    .where(AreaVersionModel.created_at < cutoff_1y)
                    .where(AreaVersionModel.area_id.in_(subquery_deleted_areas))
                )
                res_versions = await session.execute(stmt_versions)
                summary["pruned_area_versions"] = res_versions.rowcount or 0

                # 2. Purge soft-deleted areas older than 90 days (cascades to remaining versions)
                stmt_areas = (
                    delete(AreaModel)
                    .where(AreaModel.deleted_at.is_not(None))
                    .where(AreaModel.deleted_at < cutoff_90d)
                )
                res_areas = await session.execute(stmt_areas)
                summary["purged_soft_deleted_areas"] = res_areas.rowcount or 0

                # 3. Delete audit_logs older than 1 year
                stmt_audit = (
                    delete(AuditLogModel)
                    .where(AuditLogModel.created_at < cutoff_1y)
                )
                res_audit = await session.execute(stmt_audit)
                summary["deleted_audit_logs"] = res_audit.rowcount or 0

                # 4. Delete expired or revoked sessions older than 30 days
                stmt_sessions = (
                    delete(SessionModel)
                    .where(
                        (SessionModel.expires_at < cutoff_30d)
                        | (SessionModel.revoked_at.is_not(None) & (SessionModel.revoked_at < cutoff_30d))
                    )
                )
                res_sessions = await session.execute(stmt_sessions)
                summary["deleted_sessions"] = res_sessions.rowcount or 0

        logger.info("Data retention job completed successfully", **summary, instance_id=instance_id)
        return summary
    except Exception as e:
        logger.error("Data retention job failed with error", error=str(e), instance_id=instance_id)
        raise


def setup_retention_scheduler(
    session_factory: async_sessionmaker,
    redis_client: Any,
    instance_id: str,
) -> AsyncIOScheduler:
    """Configures APScheduler for daily retention execution at 02:00 UTC."""
    scheduler = AsyncIOScheduler(timezone=timezone.utc)
    scheduler.add_job(
        run_retention_job,
        trigger=CronTrigger(hour=2, minute=0, timezone=timezone.utc),
        args=[session_factory, redis_client, instance_id],
        id="data_retention_job",
        replace_existing=True,
    )
    return scheduler
