from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from snapland.core.domain.area import (
    Area,
    AreaVersion,
    Coordinate,
    CreateAreaRequest,
    UpdateAreaRequest,
)
from snapland.core.domain.events import DomainEvent
from snapland.core.domain.user import TokenResponse, User
from snapland.core.interfaces.repositories import AreaPage


class IAreaService(Protocol):
    async def create_area(self, req: CreateAreaRequest, user_id: UUID) -> Area: ...
    async def update_area(self, area_id: UUID, req: UpdateAreaRequest, user_id: UUID) -> Area: ...   # raises ConflictError(current_area)
    async def delete_area(self, area_id: UUID, user_id: UUID) -> None: ...
    async def get_areas_in_bounds(self, min_lng: float, min_lat: float, max_lng: float, max_lat: float,
                                  *, zoom: int | None = None, limit: int = 500) -> AreaPage: ...
    async def get_area(self, area_id: UUID) -> Area: ...
    async def get_history(self, area_id: UUID) -> Sequence[AreaVersion]: ...

@dataclass(frozen=True)
class PolygonValidation:
    valid: bool
    reason: str | None = None   # machine-readable, e.g. "SELF_INTERSECTION", "TOO_MANY_VERTICES"

class ISpatialService(Protocol):
    def calculate_area_km2(self, coordinates: Sequence[Coordinate]) -> float: ...          # WGS84 ellipsoid (pyproj.Geod)
    def validate_polygon(self, coordinates: Sequence[Coordinate]) -> PolygonValidation: ...
    def to_geojson_polygon(self, coordinates: Sequence[Coordinate]) -> dict: ...           # closes ring, [lng, lat] order
    def simplify_tolerance_deg(self, zoom: int | None) -> float: ...                       # 0 = no simplification

class IAuthService(Protocol):
    async def register(self, email: str, password: str, display_name: str) -> User: ...
    async def login(self, email: str, password: str, ip_address: str = "0.0.0.0") -> TokenResponse: ...                 # includes refresh token for the cookie
    async def refresh_token(self, refresh_token: str, ip_address: str = "0.0.0.0") -> TokenResponse: ...                # rotates; reuse ⇒ revoke family
    async def revoke_token(self, refresh_token: str) -> None: ...
    async def issue_ws_ticket(self, user_id: UUID) -> str: ...                             # random, TTL 30 s, single use
    async def redeem_ws_ticket(self, ticket: str) -> UUID | None: ...                      # atomic GETDEL
    def verify_access_token(self, token: str, public_key: str) -> UUID: ...

@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    retry_after_ms: int = 0

class IRateLimiter(Protocol):
    async def check_limit(self, user_id: str, bucket: str, limit: int, window_seconds: int) -> RateLimitResult: ...

class IEventPublisher(Protocol):
    """Domain events → durable stream. Called AFTER the DB transaction commits."""
    async def publish(self, event: DomainEvent) -> None: ...
