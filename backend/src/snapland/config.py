import socket
import uuid

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _generate_instance_id() -> str:
    try:
        return f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    except Exception:
        return f"snapland-{uuid.uuid4().hex[:6]}"


def _generate_dev_keys() -> tuple[str, str]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return private_pem, public_pem
    except Exception:
        return "secret_private", "secret_public"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="allow",
        case_sensitive=True,
    )

    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://snapland:password@localhost:5432/snapland"
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
            if not self.JWT_PRIVATE_KEY.startswith("-----BEGIN"):
                raise ValueError("Valid JWT_PRIVATE_KEY required in production")
        else:
            if not self.JWT_PRIVATE_KEY.startswith("-----BEGIN"):
                priv, pub = _generate_dev_keys()
                self.JWT_PRIVATE_KEY = priv
                self.JWT_PUBLIC_KEY = pub
        return self


settings = Settings()

