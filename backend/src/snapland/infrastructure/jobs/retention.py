import asyncio
from datetime import datetime, timedelta, timezone
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine
from snapland.infrastructure.db.models import AreaModel, AreaVersionModel, AuditLogModel, SessionModel

logger = structlog.get_logger(__name__)

async def run_retention_job(engine: AsyncEngine, redis):
    # Try to acquire lock
    lock_key = "lock:retention_job"
    acquired = await redis.set(lock_key, "1", nx=True, ex=3600)
    if not acquired:
        logger.info("Retention job lock not acquired, skipping")
        return

    try:
        logger.info("Starting retention job")
        now = datetime.now(timezone.utc)
        
        async with engine.begin() as conn:
            # Delete soft-deleted areas older than 90 days
            cutoff_90d = now - timedelta(days=90)
            stmt_areas = delete(AreaModel).where(AreaModel.deleted_at < cutoff_90d)
            result = await conn.execute(stmt_areas)
            logger.info("Purged soft-deleted areas", count=result.rowcount)
            
            # Delete area_versions older than 1 year for deleted areas
            cutoff_1y = now - timedelta(days=365)
            # We can just delete area_versions where area_id is not in AreaModel? 
            # Or area_versions where area was deleted > 1 year ago. 
            # Since areas are purged after 90 days, any area_version without an area is an orphan.
            # But the requirement says "Prune area_versions older than 1 year for deleted areas"
            # Actually, area_versions for areas that were soft-deleted and already purged will just be orphans.
            # Let's delete area_versions that are older than 1 year AND have no corresponding area in AreaModel.
            # Or just older than 1 year. The prompt says "for deleted areas".
            # If the area is deleted, it might be in AreaModel with deleted_at != None, or it might be purged.
            # So: delete where area_id NOT IN (select id from areas where deleted_at IS NULL) AND created_at < 1y
            stmt_versions = delete(AreaVersionModel).where(
                AreaVersionModel.created_at < cutoff_1y
            ).where(
                AreaVersionModel.area_id.not_in(
                    select(AreaModel.id).where(AreaModel.deleted_at.is_(None))
                )
            )
            result = await conn.execute(stmt_versions)
            logger.info("Pruned old area_versions", count=result.rowcount)
            
            # Delete audit_logs older than 1 year
            stmt_audit = delete(AuditLogModel).where(AuditLogModel.created_at < cutoff_1y)
            result = await conn.execute(stmt_audit)
            logger.info("Deleted old audit_logs", count=result.rowcount)
            
            # Delete expired/revoked sessions older than 30 days
            cutoff_30d = now - timedelta(days=30)
            stmt_sessions = delete(SessionModel).where(
                (SessionModel.expires_at < cutoff_30d) | 
                (SessionModel.revoked_at < cutoff_30d)
            )
            result = await conn.execute(stmt_sessions)
            logger.info("Deleted old sessions", count=result.rowcount)
            
    except Exception as e:
        logger.error("Retention job failed", exc_info=True)
    finally:
        # We can let the lock expire or delete it. Since it runs daily, deleting is fine.
        await redis.delete(lock_key)

def start_retention_scheduler(engine: AsyncEngine, redis):
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_retention_job, 
        'cron', 
        hour=2, 
        minute=0, 
        timezone='UTC', 
        args=[engine, redis]
    )
    scheduler.start()
    return scheduler
