
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession

# Async session maker
from app.db.session import AsyncSessionLocal

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """ Dependency to yield and async database sesssion per request. """
    async with  AsyncSessionLocal() as session:
        yield session