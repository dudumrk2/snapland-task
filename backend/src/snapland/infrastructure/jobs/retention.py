import asyncio
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
RETENTION_LOCK_TTL = 3600  # 1 hour TTL fail-safe
BATCH_SIZE = 1000


async def run_retention_job(
    session_factory: async_sessionmaker,
    redis_client: Any,
    instance_id: str,
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    """Runs data retention tasks guarded by Redis distributed SET NX lock.

    Tasks:
    1. Prune area_versions older than 1 year for deleted areas.
    2. Purge soft-deleted areas older than 90 days.
    3. Delete audit_logs older than 1 year.
    4. Delete expired/revoked sessions older than 30 days.

    Each task runs in bounded batches with separate transactions to avoid holding
    locks for extended durations and to prevent statement timeout errors.
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
        # Task 1: Prune area_versions older than 1 year for deleted areas
        while True:
            async with session_factory() as session:
                subquery_deleted_areas = (
                    select(AreaVersionModel.id)
                    .join(AreaModel, AreaVersionModel.area_id == AreaModel.id)
                    .where(AreaModel.deleted_at.is_not(None))
                    .where(AreaVersionModel.created_at < cutoff_1y)
                    .limit(batch_size)
                )
                stmt = delete(AreaVersionModel).where(AreaVersionModel.id.in_(subquery_deleted_areas))
                res = await session.execute(stmt)
                await session.commit()
                count = res.rowcount or 0
                summary["pruned_area_versions"] += count
                if count < batch_size:
                    break

        # Task 2: Purge soft-deleted areas older than 90 days (cascades to remaining versions)
        while True:
            async with session_factory() as session:
                subquery_areas = (
                    select(AreaModel.id)
                    .where(AreaModel.deleted_at.is_not(None))
                    .where(AreaModel.deleted_at < cutoff_90d)
                    .limit(batch_size)
                )
                stmt = delete(AreaModel).where(AreaModel.id.in_(subquery_areas))
                res = await session.execute(stmt)
                await session.commit()
                count = res.rowcount or 0
                summary["purged_soft_deleted_areas"] += count
                if count < batch_size:
                    break

        # Task 3: Delete audit_logs older than 1 year
        while True:
            async with session_factory() as session:
                subquery_audit = (
                    select(AuditLogModel.id)
                    .where(AuditLogModel.created_at < cutoff_1y)
                    .limit(batch_size)
                )
                stmt = delete(AuditLogModel).where(AuditLogModel.id.in_(subquery_audit))
                res = await session.execute(stmt)
                await session.commit()
                count = res.rowcount or 0
                summary["deleted_audit_logs"] += count
                if count < batch_size:
                    break

        # Task 4: Delete expired or revoked sessions older than 30 days
        while True:
            async with session_factory() as session:
                subquery_sessions = (
                    select(SessionModel.id)
                    .where(
                        (SessionModel.expires_at < cutoff_30d)
                        | (SessionModel.revoked_at.is_not(None) & (SessionModel.revoked_at < cutoff_30d))
                    )
                    .limit(batch_size)
                )
                stmt = delete(SessionModel).where(SessionModel.id.in_(subquery_sessions))
                res = await session.execute(stmt)
                await session.commit()
                count = res.rowcount or 0
                summary["deleted_sessions"] += count
                if count < batch_size:
                    break

        logger.info("Data retention job completed successfully", **summary, instance_id=instance_id)
        return summary
    except Exception as e:
        logger.error("Data retention job failed with error", error=str(e), instance_id=instance_id)
        raise
    finally:
        try:
            val = await redis_client.get(RETENTION_LOCK_KEY)
            if val == instance_id or (isinstance(val, bytes) and val.decode() == instance_id):
                await redis_client.delete(RETENTION_LOCK_KEY)
        except Exception as e:
            logger.warning("Failed to release retention Redis lock", error=str(e))


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
