import os
import socket
import tempfile
import uuid
from pathlib import Path

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _generate_instance_id() -> str:
    try:
        return f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    except Exception:
        return f"snapland-{uuid.uuid4().hex[:6]}"


def _get_or_create_dev_keys() -> tuple[str, str]:
    """Generates or loads a local development RSA-2048 keypair.

    Persists to a temporary/ignored file so multiple uvicorn workers
    share the identical keypair without committing secrets to version control.
    """
    temp_dir = Path(tempfile.gettempdir())
    priv_path = temp_dir / "snapland_dev_jwt_priv.pem"
    pub_path = temp_dir / "snapland_dev_jwt_pub.pem"

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    if priv_path.exists() and pub_path.exists():
        try:
            priv_content = priv_path.read_text(encoding="utf-8")
            pub_content = pub_path.read_text(encoding="utf-8")
            serialization.load_pem_private_key(priv_content.encode("utf-8"), password=None)
            serialization.load_pem_public_key(pub_content.encode("utf-8"))
            return priv_content, pub_content
        except Exception:
            pass

    try:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        priv_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")
        pub_pem = key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        # Atomic write to temporary files with secure permissions (0o600 for private key)
        priv_tmp = priv_path.with_suffix(f".tmp.{uuid.uuid4().hex[:6]}")
        pub_tmp = pub_path.with_suffix(f".tmp.{uuid.uuid4().hex[:6]}")

        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd_priv = os.open(str(priv_tmp), flags, 0o600)
        with open(fd_priv, "w", encoding="utf-8", closefd=True) as f:
            f.write(priv_pem)

        fd_pub = os.open(str(pub_tmp), flags, 0o644)
        with open(fd_pub, "w", encoding="utf-8", closefd=True) as f:
            f.write(pub_pem)

        os.replace(priv_tmp, priv_path)
        os.replace(pub_tmp, pub_path)
        return priv_pem, pub_pem
    except Exception as e:
        raise RuntimeError(f"Failed to generate dev JWT keys: {e}") from e


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="ignore",
        case_sensitive=True,
    )

    ENVIRONMENT: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://snapland:password@localhost:5432/snapland"
    REDIS_URL: str = "redis://localhost:6379"
    JWT_PRIVATE_KEY: str = ""
    JWT_PUBLIC_KEY: str = ""
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
    def validate_environment_settings(self) -> "Settings":
        if self.ENVIRONMENT in ("production", "staging"):
            if self.WS_ALLOWED_ORIGINS == "*":
                raise ValueError(f"WS_ALLOWED_ORIGINS cannot be '*' in {self.ENVIRONMENT}")
            if not self.JWT_PRIVATE_KEY or not self.JWT_PRIVATE_KEY.startswith("-----BEGIN"):
                raise ValueError(f"Valid JWT_PRIVATE_KEY required in {self.ENVIRONMENT}")
            if not self.JWT_PUBLIC_KEY or not self.JWT_PUBLIC_KEY.startswith("-----BEGIN"):
                raise ValueError(f"Valid JWT_PUBLIC_KEY required in {self.ENVIRONMENT}")
            if "localhost" in self.DATABASE_URL or "snapland:password" in self.DATABASE_URL:
                raise ValueError(f"Default development DATABASE_URL cannot be used in {self.ENVIRONMENT}")
        else:
            if not self.JWT_PRIVATE_KEY or not self.JWT_PRIVATE_KEY.startswith("-----BEGIN"):
                priv, pub = _get_or_create_dev_keys()
                self.JWT_PRIVATE_KEY = priv
                self.JWT_PUBLIC_KEY = pub
        return self


settings = Settings()
