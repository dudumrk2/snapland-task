from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from snapland.core.domain.area import Area, Coordinate

class PresenceUser(BaseModel):
    user_id: UUID
    display_name: str

# ---------------------------------------------------------
# Client -> Server Messages
# ---------------------------------------------------------

class DrawStartPayload(BaseModel):
    shapeId: str
    point: Coordinate

class DrawStartMessage(BaseModel):
    type: Literal["DRAW_START"] = "DRAW_START"
    payload: DrawStartPayload

class DrawUpdatePayload(BaseModel):
    shapeId: str
    seq: int
    fromIndex: int
    append: list[Coordinate]

class DrawUpdateMessage(BaseModel):
    type: Literal["DRAW_UPDATE"] = "DRAW_UPDATE"
    payload: DrawUpdatePayload

class DrawCommitPayload(BaseModel):
    shapeId: str
    name: str
    points: list[Coordinate]

class DrawCommitMessage(BaseModel):
    type: Literal["DRAW_COMMIT"] = "DRAW_COMMIT"
    payload: DrawCommitPayload

class DrawCancelPayload(BaseModel):
    shapeId: str

class DrawCancelMessage(BaseModel):
    type: Literal["DRAW_CANCEL"] = "DRAW_CANCEL"
    payload: DrawCancelPayload

class CursorMoveClientPayload(BaseModel):
    lat: float
    lng: float

class CursorMoveClientMessage(BaseModel):
    type: Literal["CURSOR_MOVE"] = "CURSOR_MOVE"
    payload: CursorMoveClientPayload

ClientMessage = (
    DrawStartMessage
    | DrawUpdateMessage
    | DrawCommitMessage
    | DrawCancelMessage
    | CursorMoveClientMessage
)

# ---------------------------------------------------------
# Server -> Client Messages
# ---------------------------------------------------------

class RemoteDrawPayload(BaseModel):
    userId: UUID
    shapeId: str
    phase: Literal["start", "update", "commit", "cancel"]
    seq: int | None = None
    fromIndex: int | None = None
    append: list[Coordinate] | None = None
    name: str | None = None
    points: list[Coordinate] | None = None

class RemoteDrawMessage(BaseModel):
    type: Literal["REMOTE_DRAW"] = "REMOTE_DRAW"
    payload: RemoteDrawPayload

class CursorMoveServerPayload(BaseModel):
    userId: UUID
    lat: float
    lng: float

class CursorMoveServerMessage(BaseModel):
    type: Literal["CURSOR_MOVE"] = "CURSOR_MOVE"
    payload: CursorMoveServerPayload

class AreaSavedPayload(BaseModel):
    area: Area
    shapeId: str | None = None

class AreaSavedMessage(BaseModel):
    type: Literal["AREA_SAVED"] = "AREA_SAVED"
    eventId: str
    payload: AreaSavedPayload

class AreaUpdatedPayload(BaseModel):
    area: Area

class AreaUpdatedMessage(BaseModel):
    type: Literal["AREA_UPDATED"] = "AREA_UPDATED"
    eventId: str
    payload: AreaUpdatedPayload

class AreaDeletedPayload(BaseModel):
    areaId: UUID

class AreaDeletedMessage(BaseModel):
    type: Literal["AREA_DELETED"] = "AREA_DELETED"
    eventId: str
    payload: AreaDeletedPayload

class PresenceSnapshotPayload(BaseModel):
    users: list[PresenceUser]

class PresenceSnapshotMessage(BaseModel):
    type: Literal["PRESENCE_SNAPSHOT"] = "PRESENCE_SNAPSHOT"
    payload: PresenceSnapshotPayload

class UserJoinedPayload(BaseModel):
    user: PresenceUser

class UserJoinedMessage(BaseModel):
    type: Literal["USER_JOINED"] = "USER_JOINED"
    payload: UserJoinedPayload

class UserLeftPayload(BaseModel):
    userId: UUID

class UserLeftMessage(BaseModel):
    type: Literal["USER_LEFT"] = "USER_LEFT"
    payload: UserLeftPayload

class ResyncRequiredPayload(BaseModel):
    reason: str | None = None

class ResyncRequiredMessage(BaseModel):
    type: Literal["RESYNC_REQUIRED"] = "RESYNC_REQUIRED"
    payload: ResyncRequiredPayload | None = None

class ErrorPayload(BaseModel):
    code: str
    message: str | None = None
    retryAfterMs: int | None = None

class ErrorMessage(BaseModel):
    type: Literal["ERROR"] = "ERROR"
    payload: ErrorPayload

ServerMessage = (
    RemoteDrawMessage
    | CursorMoveServerMessage
    | AreaSavedMessage
    | AreaUpdatedMessage
    | AreaDeletedMessage
    | PresenceSnapshotMessage
    | UserJoinedMessage
    | UserLeftMessage
    | ResyncRequiredMessage
    | ErrorMessage
)
