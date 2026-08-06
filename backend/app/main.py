import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from app.core.config import settings
from app.api.v1.endpoints import sentiment, search
from app.api.deps import RATE_LIMIT_MAX_REQUESTS
from app.db.vector_store import init_qdrant_collection

logger = logging.getLogger(__name__)

# --- Swagger UI: disabled in production to avoid exposing attack surface ---
docs_url = "/docs" if settings.ENVIRONMENT != "production" else None
redoc_url = "/redoc" if settings.ENVIRONMENT != "production" else None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Ensures the Qdrant collection and its payload indexes exist before the API
    serves traffic. Without this, an API booting against a fresh Qdrant answered
    /search/semantic with HTTP 500 until the vectorization backfill happened to
    create the collection.

    init_qdrant_collection is idempotent and synchronous (the Qdrant client is
    blocking), so it runs in a worker thread to keep the event loop free.

    Failure is deliberately non-fatal: /health and /sentiment do not depend on
    Qdrant, so a vector-store outage degrades semantic search instead of taking
    the whole API down.
    """
    try:
        await asyncio.to_thread(init_qdrant_collection)
    except Exception as e:
        logger.warning(
            f"Qdrant initialization failed at startup: {e}. "
            "Semantic search will be unavailable until Qdrant recovers."
        )
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Institutional-grade sentiment analysis API for financial markets.",
    version="1.0.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    lifespan=lifespan,
)


@app.middleware("http")
async def inject_rate_limit_headers(request: Request, call_next):
    """
    Global middleware that reads rate limit metadata stored in request.state
    by verify_api_key and injects standard X-RateLimit-* headers into every
    authenticated response. Unauthenticated endpoints pass through unmodified.
    """
    response = await call_next(request)

    if hasattr(request.state, "ratelimit_remaining"):
        response.headers["X-RateLimit-Limit"] = str(RATE_LIMIT_MAX_REQUESTS)
        response.headers["X-RateLimit-Remaining"] = str(request.state.ratelimit_remaining)
        response.headers["X-RateLimit-Reset"] = str(request.state.ratelimit_reset)

    return response


app.include_router(sentiment.router, prefix="/api/v1/sentiment", tags=["Sentiment Analysis"])
app.include_router(search.router, prefix="/api/v1/search", tags=["Semantic Search"])

@app.get("/")
def root():
    return {"message": "Welcome to Syndra API", "docs": "/docs"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "syndra-api"}