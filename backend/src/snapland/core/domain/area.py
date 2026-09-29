from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class Coordinate(BaseModel):
    lat: float
    lng: float

class Area(BaseModel):
    id: UUID
    name: str
    coordinates: list[Coordinate]
    area_km2: float
    version: int
    created_by: UUID
    last_edited_by: UUID
    created_at: datetime
    updated_at: datetime

class AreaVersion(BaseModel):
    version_number: int
    edited_by: UUID
    change_type: str
    area_km2: float
    created_at: datetime
    diff: dict[str, Any]

class CreateAreaRequest(BaseModel):
    name: str
    coordinates: list[Coordinate]

class UpdateAreaRequest(BaseModel):
    version: int
    name: str | None = None
    coordinates: list[Coordinate] | None = None
