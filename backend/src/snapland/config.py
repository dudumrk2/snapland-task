from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/snapland"
    REDIS_URL: str = "redis://localhost:6379"
    JWT_PRIVATE_KEY: str = "secret_private"
    JWT_PUBLIC_KEY: str = "secret_public"
    INSTANCE_ID: str = "local"
    WS_ALLOWED_ORIGINS: str = "*"
    MAX_AREA_KM2: float = 1000.0
    MAX_POLYGON_VERTICES: int = 1000

    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()
