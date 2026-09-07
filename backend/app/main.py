import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator

from app.core.config import settings
from app.core.metrics import refresh_domain_metrics
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


# Instrumented but NOT exposed by the library: .expose() would mount its own
# bare endpoint, and the domain gauges need a refresh awaited before the
# registry is serialised. The /metrics route below does both.
#
# The scrape itself is excluded from the histograms. At a 15s interval it would
# be the single most frequent request on the box and would drag every throughput
# and latency figure towards the cost of serialising the registry.
Instrumentator(
    excluded_handlers=["/metrics"],
    should_instrument_requests_inprogress=True,
    inprogress_labels=True,
).instrument(app)


@app.get("/metrics", include_in_schema=False)
async def metrics_endpoint():
    """
    Prometheus scrape target. Reachable only from inside syndra_net: Caddy
    returns 403 for this path, because the response describes internal routes,
    latencies and business volumes.
    """
    await refresh_domain_metrics()
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(sentiment.router, prefix="/api/v1/sentiment", tags=["Sentiment Analysis"])
app.include_router(search.router, prefix="/api/v1/search", tags=["Semantic Search"])

@app.get("/")
def root():
    return {"message": "Welcome to Syndra API", "docs": "/docs"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "syndra-api"}