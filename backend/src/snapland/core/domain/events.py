from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from snapland.core.domain.area import Area


class DomainEvent(BaseModel):
    pass

class AreaCreated(DomainEvent):
    area_id: UUID
    created_at: datetime
    created_by: UUID
    area: Area | None = None
    shape_id: str | None = None

class AreaUpdated(DomainEvent):
    area_id: UUID
    version: int
    updated_at: datetime
    updated_by: UUID
    area: Area | None = None

class AreaDeleted(DomainEvent):
    area_id: UUID
    deleted_at: datetime
    deleted_by: UUID
