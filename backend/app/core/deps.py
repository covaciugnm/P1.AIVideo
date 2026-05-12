"""FastAPI dependency providers."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_sessionmaker


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    sm = get_sessionmaker()
    async with sm() as session:
        yield session
