import uuid
from typing import Any
from datetime import datetime, timezone

class AuditService:
    def __init__(self, publish_fn: Any = None) -> None:
        self.publish = publish_fn

    async def log_event(self, user_id: uuid.UUID, action: str, entity_type: str, entity_id: uuid.UUID, payload: dict[str, Any], ip_address: str) -> None:
        from snapland.infrastructure.db.session import SessionLocal
        from snapland.infrastructure.db.models import AuditLogModel
        
        async with SessionLocal() as session:
            model = AuditLogModel(
                id=uuid.uuid4(),
                user_id=user_id,
                action=action,
                resource_type=entity_type,
                resource_id=entity_id,
                details=payload,
                created_at=datetime.now(timezone.utc)
            )
            session.add(model)
            await session.commit()
