from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from snapland.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
