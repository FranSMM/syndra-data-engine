from fastapi import Security, HTTPException, status, Depends
from fastapi.security import APIKeyHeader
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

# Async session maker
from app.db.session import AsyncSessionLocal

from app.core.security import get_api_key_hash
from app.models.api_key import APIKey
from app.core.redis import redis_client

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """ Dependency to yield and async database sesssion per request. """
    async with  AsyncSessionLocal() as session:
        yield session

async def verify_api_key(
    api_key: str = Security(APIKeyHeader(name="X-API-Key", auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> APIKey:
    """
    Middleware B2B: Converts raw API key to hash and validates it against the database.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing 'X-API-Key' header",
        )
    
    incoming_hash = get_api_key_hash(api_key)
    cached_key = f"auth:{incoming_hash}"
    
    # Redis Cache
    cached_client_name = await redis_client.get(cached_key)
    if cached_client_name:

        # Return a memory object (not linked to Postgres)
        return APIKey(hashed_key=incoming_hash, client_name=cached_client_name, is_active=True)

    # PostgreSQL search (Cache Miss)
    stmt = select(APIKey).where(
        APIKey.hashed_key == incoming_hash,
        APIKey.is_active == True
    )
    result = await db.execute(stmt)
    key_record = result.scalars().first()

    if not key_record:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or revoked API Key"
        )

    # Rate Limiting (Redis)
    # Set the API key in Redis with a TTL of 5 minutes
    await redis_client.set(cached_key, key_record.client_name, ex=60*5)

    return key_record