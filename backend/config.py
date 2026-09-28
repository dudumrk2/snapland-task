from typing import List, Union

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://user:pass@localhost:5432/snapland"
    redis_url: str = "redis://localhost:6379/0"
    jwt_private_key: str = "---BEGIN PRIVATE KEY---"
    jwt_public_key: str = "---BEGIN PUBLIC KEY---"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: Union[str, List[str]] = "http://localhost:5173"
    ws_allowed_origins: Union[str, List[str]] = "http://localhost:5173"
    instance_id: str = "local_dev"
    max_area_km2: int = 100
    max_polygon_vertices: int = 500

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins_list(self) -> List[str]:
        if isinstance(self.cors_origins, str):
            return [x.strip() for x in self.cors_origins.split(",") if x.strip()]
        return self.cors_origins

    @property
    def ws_allowed_origins_list(self) -> List[str]:
        if isinstance(self.ws_allowed_origins, str):
            return [x.strip() for x in self.ws_allowed_origins.split(",") if x.strip()]
        return self.ws_allowed_origins


settings = Settings()
