from datetime import datetime, timezone

from fastapi import Request, Security, HTTPException, status, Depends
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

# Counter increment + TTL setup must happen in a single atomic step. Issuing
# INCR and EXPIRE as separate round-trips leaves a window where a crash (or a
# connection drop) between the two orphans the key with no TTL: Redis keeps it
# forever and that client stays permanently at HTTP 429.
# Lua scripts run atomically inside Redis, which closes that window and collapses
# the three round-trips (INCR + EXPIRE + TTL) into one.
# The `ttl < 0` branch is self-healing: it re-arms the window on any key left
# without a TTL.
_RATE_LIMIT_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if current == 1 or ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
    ttl = tonumber(ARGV[1])
end
return {current, ttl}
"""

# register_script performs no I/O at import time: it only builds the Script
# wrapper, which then uses EVALSHA with an automatic EVAL fallback.
_rate_limit_script = redis_client.register_script(_RATE_LIMIT_SCRIPT)


async def _enforce_rate_limit(api_key_hash: str) -> tuple[int, int]:
    """
    Atomic rate limiter backed by a Redis Lua script (INCR + EXPIRE + TTL).
    Returns (remaining_requests, seconds_until_reset).
    Raises HTTP 429 if the client exceeds RATE_LIMIT_MAX_REQUESTS per window.
    """
    rate_key = f"ratelimit:{api_key_hash}"

    current_count, ttl = await _rate_limit_script(
        keys=[rate_key], args=[RATE_LIMIT_WINDOW_SECONDS]
    )

    remaining = max(RATE_LIMIT_MAX_REQUESTS - current_count, 0)

    if current_count > RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {RATE_LIMIT_MAX_REQUESTS} requests per {RATE_LIMIT_WINDOW_SECONDS}s.",
            headers={"Retry-After": str(max(ttl, 1))}
        )

    return remaining, max(ttl, 0)


async def verify_api_key(
    request: Request,
    api_key: str = Security(APIKeyHeader(name="X-API-Key", auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> APIKey:
    """
    Middleware B2B: Converts raw API key to hash and validates it against the database.
    Stores rate limit metadata in request.state for header injection by middleware.
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
        remaining, reset = await _enforce_rate_limit(incoming_hash)
        request.state.ratelimit_remaining = remaining
        request.state.ratelimit_reset = reset
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

    # --- 3. Expiration Check (Trial Keys) ---
    if key_record.expires_at and key_record.expires_at <= datetime.now(timezone.utc):
        # Auto-deactivate the expired trial key to avoid repeated DB lookups
        key_record.is_active = False
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key has expired. Contact support to renew.",
        )

    # Cache the auth result in Redis.
    # For trial keys, cap TTL to remaining lifetime to prevent serving
    # stale auth after expiration. Permanent keys use the default 5 min.
    cache_ttl = 60 * 5
    if key_record.expires_at:
        remaining = int((key_record.expires_at - datetime.now(timezone.utc)).total_seconds())
        cache_ttl = max(min(cache_ttl, remaining), 1)
    await redis_client.set(cached_key, key_record.client_name, ex=cache_ttl)
    # Rate limit AFTER confirming identity
    remaining, reset = await _enforce_rate_limit(incoming_hash)
    request.state.ratelimit_remaining = remaining
    request.state.ratelimit_reset = reset

    return key_record