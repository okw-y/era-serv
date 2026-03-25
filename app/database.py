import os

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from typing import Any, AsyncGenerator


engine = create_async_engine(os.environ["DB_LOCATION"], echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession | Any, Any]:
    async with AsyncSessionLocal() as session:
        yield session
