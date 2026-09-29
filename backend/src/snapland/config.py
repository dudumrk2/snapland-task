from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    INSTANCE_ID: str = "local"
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


settings = Settings()
