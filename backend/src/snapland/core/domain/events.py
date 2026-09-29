from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DomainEvent(BaseModel):
    pass

class AreaCreated(DomainEvent):
    area_id: UUID
    created_at: datetime
    created_by: UUID

class AreaUpdated(DomainEvent):
    area_id: UUID
    version: int
    updated_at: datetime
    updated_by: UUID

class AreaDeleted(DomainEvent):
    area_id: UUID
    deleted_at: datetime
    deleted_by: UUID
