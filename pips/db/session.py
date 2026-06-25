from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from pips.db.engine import async_session


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session() as session:
        yield session
