from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base

from src.utils.settings import settings


BASE = declarative_base()
engine = create_async_engine(url=settings.DB_CONNECTION, echo=False)
Local_Session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with Local_Session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
