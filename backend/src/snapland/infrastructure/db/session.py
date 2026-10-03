from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from snapland.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args={
        "server_settings": {
            "statement_timeout": "30000",
        }
    },
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
