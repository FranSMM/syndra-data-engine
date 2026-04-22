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

RATE_LIMIT_MAX_REQUESTS = 100  # requests per window
RATE_LIMIT_WINDOW_SECONDS = 60  # 1-minute sliding window


async def _enforce_rate_limit(api_key_hash: str) -> None:
    """
    Atomic rate limiter using Redis INCR + EXPIRE.
    Raises HTTP 429 if the client exceeds RATE_LIMIT_MAX_REQUESTS per window.
    """
    rate_key = f"ratelimit:{api_key_hash}"

    # INCR is atomic: creates the key with value 1 if it doesn't exist
    current_count = await redis_client.incr(rate_key)

    # Set TTL only on the FIRST request of the window (when count == 1)
    if current_count == 1:
        await redis_client.expire(rate_key, RATE_LIMIT_WINDOW_SECONDS)

    if current_count > RATE_LIMIT_MAX_REQUESTS:
        ttl = await redis_client.ttl(rate_key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS}s.",
            headers={"Retry-After": str(max(ttl, 1))}
        )


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
    
    # --- 1. Auth: Redis Cache Hit ---
    cached_client_name = await redis_client.get(cached_key)
    if cached_client_name:
        # Rate limit AFTER confirming identity (don't let invalid keys consume budget)
        await _enforce_rate_limit(incoming_hash)
        return APIKey(hashed_key=incoming_hash, client_name=cached_client_name, is_active=True)

    # --- 2. Auth: PostgreSQL Lookup (Cache Miss) ---
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

    # Cache the auth result in Redis (5 min TTL)
    await redis_client.set(cached_key, key_record.client_name, ex=60*5)

    # Rate limit AFTER confirming identity
    await _enforce_rate_limit(incoming_hash)

    return key_record