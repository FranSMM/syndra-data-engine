from redis import asyncio as aioredis
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Initialize the Redis client
# decode_responses=True means that the client will decode the responses from Redis to strings
redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)