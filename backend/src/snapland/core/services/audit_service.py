import uuid
from typing import Any

class AuditService:
    def __init__(self, publish_fn: Any = None) -> None:
        self.publish = publish_fn

    async def log_event(self, user_id: uuid.UUID, action: str, entity_type: str, entity_id: uuid.UUID, payload: dict[str, Any], ip_address: str) -> None:
        pass
