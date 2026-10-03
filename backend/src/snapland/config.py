import socket
import uuid

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _generate_instance_id() -> str:
    try:
        return f"{socket.gethostname()}-{uuid.uuid4().hex[:6]}"
    except Exception:
        return f"snapland-{uuid.uuid4().hex[:6]}"


# Static RSA-2048 keypair reserved EXCLUSIVELY for local development and unit tests.
# Guarantees that multiple uvicorn workers and test suites share the same verification key.
INSECURE_DEV_JWT_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC/HvFJOIM9CN1K
P1gmw8k+2Ru/nSOXrJCkNZ+ADM2edoqwBsZgKL7R7bvx5PEU0mOX3JJ5CUg1Rxme
GSQdQXss7UrFZfN9kIuxIrgEK2mlTXGPKL6wpvF688OSDSHep16zeVbZWiX74oi0
MA7E5tylw7lvz9NUCgVHfHCc+OjoSZ21enF9WClKxyB4Kg8Tcu66SYlSerTnjFxR
EAeciEz7yMaYP6wwqo/JHj/rhWXg1U0GIxGC1F7dIwybUKMG4zCJMcSgeNvEObg5
JcAS2oEU+5Y0AmuI7LTIOxLsAPE85MVFXh6s360eHeYNTyFjW9DPMaFyn/pzcw59
1H15RcPfAgMBAAECggEAPncyjaf23QAEs7u4aBMdt3jmZN5LP8ubCtCr7QJCQkSk
V5wfQlaO57Y383vMf+2zt3LUPNMX0rIGYXH+J8G7LJfyFEqaJrQTtDWQx2wY/3os
X4oFqV8nFfSOOzInm8pAXZCPHkMknwsPezUp3plGDLfH6A+ZFqKfzxmRBP0lwqWc
CI/8HXp33wlZFNAgnFp41hKUhUBIN/vzMBnATif4SvjzczJ8QkWNke2Osw/7CoN/
S0okcNWfeK7l/zM9VLbjjc4D7BUlRg+4GgxlOuELBsLlVYnhVrAtw66VEV8bJepH
s/vsvOmOgp4n98h6Msh5XxQJx7oapRPwmgGliCMqQQKBgQDsbb5nApM3wy+vrePZ
/kQzJrsb12lIHXLZWcoZ0ezr4ThoGCWbiPoa5Yn6WGLihqwFBEHIFblgPHIk1hOD
zL6darscs3+u4ZU9YF5NBytSjSdW65hfecsTGw5GgfBFPqGYqeubs64SLzNMM4Xq
0cm7cJ1ZfL1Mx6teQ8aybBYhZwKBgQDO8Q/61F/Rbxm1v4DlVkHXP9r7RlQk7yWq
Bct+TzeIE//rPSaMgsL1lp9OssAOSzcr0QFeI2l882oe6cuf670ep+LqWcQ89SGo
SfouEhAoLLxwU4/4c7JVkkGVxdmkJA9JHsY1/v+nsgD9sZ+xrWjTQmeex1LyI4Ct
PVNbKiXmyQKBgBHYut2luR0lc60MMD3dTqKZ0tfoK79Q0cGMYJAQY5TunEZnRDd4
YIC1QPQPxe8ZgVSjnJ+Q3Dxic69KJZD2XJEfZF5nQkUeLBjE9HlWCDQkCYsrH4Zd
eDHKAgradhuT/bi7YtiO+J3QyEuBPCOckGDAwG/n1ZY9IDduYEpJlGYTAoGBALVT
su3VQzRPRlbju3y4jS6fzDBa2oYWaolFVJ6TqRP6ekdUqL98IHpzBZo+tFyR+YDS
PYGQQ/FxlG4L7BlvxaHj98fi6jmDjX9Zevb9atzY/jDqd397WSrz4bXrzB2wXxhx
97n+e2MkbQvepRBZ4z0htYwCGaMECs9BqhV6pAVJAoGBAITlQS6zHW4em83LWSS6
5oJBIQ2tfn+r2MEdQ1PGt04BIsNvThSGqE+u8QU3kTLWoUBUJkYvNekeFKQAPWDC
PyG5gPD9o4NcTLKUiQmrSIpPE7H9b7uY1mj+sbazSkaE8clqMXUABPXon+Oocn9t
ewuu0geG+cydSMO0T/AOqJzE
-----END PRIVATE KEY-----"""

INSECURE_DEV_JWT_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvx7xSTiDPQjdSj9YJsPJ
Ptkbv50jl6yQpDWfgAzNnnaKsAbGYCi+0e278eTxFNJjl9ySeQlINUcZnhkkHUF7
LO1KxWXzfZCLsSK4BCtppU1xjyi+sKbxevPDkg0h3qdes3lW2Vol++KItDAOxObc
pcO5b8/TVAoFR3xwnPjo6EmdtXpxfVgpSscgeCoPE3LuukmJUnq054xcURAHnIhM
+8jGmD+sMKqPyR4/64Vl4NVNBiMRgtRe3SMMm1CjBuMwiTHEoHjbxDm4OSXAEtqB
FPuWNAJriOy0yDsS7ADxPOTFRV4erN+tHh3mDU8hY1vQzzGhcp/6c3MOfdR9eUXD
3wIDAQAB
-----END PUBLIC KEY-----"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="allow",
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
    def validate_production_settings(self) -> "Settings":
        if self.ENVIRONMENT == "production":
            if self.WS_ALLOWED_ORIGINS == "*":
                raise ValueError("WS_ALLOWED_ORIGINS cannot be '*' in production")
            if not self.JWT_PRIVATE_KEY or not self.JWT_PRIVATE_KEY.startswith("-----BEGIN"):
                raise ValueError("Valid JWT_PRIVATE_KEY required in production")
            if not self.JWT_PUBLIC_KEY or not self.JWT_PUBLIC_KEY.startswith("-----BEGIN"):
                raise ValueError("Valid JWT_PUBLIC_KEY required in production")
            if self.JWT_PRIVATE_KEY == INSECURE_DEV_JWT_PRIVATE_KEY:
                raise ValueError("Cannot use default insecure development keys in production")
            if "localhost" in self.DATABASE_URL or "password" in self.DATABASE_URL:
                raise ValueError("Default development DATABASE_URL cannot be used in production")
        else:
            if not self.JWT_PRIVATE_KEY or not self.JWT_PRIVATE_KEY.startswith("-----BEGIN"):
                self.JWT_PRIVATE_KEY = INSECURE_DEV_JWT_PRIVATE_KEY
                self.JWT_PUBLIC_KEY = INSECURE_DEV_JWT_PUBLIC_KEY
        return self


settings = Settings()
