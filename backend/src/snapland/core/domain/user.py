from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

class User(BaseModel):
    id: UUID
    email: str
    display_name: str
    password_hash: str | None = None

class Session(BaseModel):
    id: UUID
    user_id: UUID
    family_id: UUID
    refresh_token_hash: str
    expires_at: datetime
    revoked_at: datetime | None = None
    ip_address: str
    created_at: datetime

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    display_name: str
    password_hash: str | None = None

class LoginRequest(BaseModel):
    email: str
    password: str
