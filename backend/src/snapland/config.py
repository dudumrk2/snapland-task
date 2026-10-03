import socket
import uuid

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _generate_instance_id() -> str:
    try:
        return f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    except Exception:
        return f"snapland-{uuid.uuid4().hex[:6]}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="allow",
        case_sensitive=True,
    )

    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/snapland"
    REDIS_URL: str = "redis://localhost:6379"
    JWT_PRIVATE_KEY: str = "secret_private"
    JWT_PUBLIC_KEY: str = "secret_public"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    INSTANCE_ID: str = _generate_instance_id()
    WS_ALLOWED_ORIGINS: str = "*"
    MAX_AREA_KM2: float = 1000.0
    MAX_POLYGON_VERTICES: int = 1000

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def ensure_asyncpg_driver(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.WS_ALLOWED_ORIGINS == "*":
                raise ValueError("WS_ALLOWED_ORIGINS cannot be '*' in production")
        return self


settings = Settings()
