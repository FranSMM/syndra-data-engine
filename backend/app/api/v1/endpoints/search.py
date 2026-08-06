import asyncio
import hashlib
import json
import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, Query, HTTPException, Depends
from qdrant_client.models import Filter, FieldCondition, MatchValue

from app.db.vector_store import qdrant, COLLECTION_NAME
from app.services.embedding_service import get_embedding_engine
from app.api.deps import verify_api_key
from app.models.api_key import APIKey
from app.core.redis import redis_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Matches the sentiment endpoint TTL. Semantic results only change when the
# vectorization backfill runs (hourly), so 5 minutes never serves stale data.
SEARCH_CACHE_TTL_SECONDS = 300


def _build_cache_key(client_name: str, query: str, ticker: Optional[str], limit: int) -> str:
    """
    Free-text queries cannot go into a Redis key verbatim: they carry arbitrary
    length, whitespace and separators. We fingerprint the normalized query
    instead, which also collapses trivial casing/spacing variants onto one entry.
    Scoped per-client, consistent with ADR 032.
    """
    fingerprint = hashlib.sha256(query.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"search:{client_name}:{fingerprint}:{(ticker or '-').upper()}:{limit}"


@router.get("/semantic", response_model=List[Dict[str, Any]])
async def semantic_search(
    query: str = Query(..., min_length=3, description="Semantic concept to search for"),
    ticker: Optional[str] = Query(None, description="Filter by specific ticker"),
    limit: int = Query(default=5, ge=1, le=20, description="Maximum number of results"),
    client: APIKey = Depends(verify_api_key)
):
    """
    Perform a semantic similarity search across financial news
    """
    logger.info(f"Search API | Client: {client.client_name} | Query: {query} | Ticker: {ticker}")

    cache_key = _build_cache_key(client.client_name, query, ticker, limit)
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        logger.info(f"CACHE HIT: Semantic search served from Redis ({query!r})")
        return json.loads(cached_data)

    logger.info(f"CACHE MISS: Computing embedding + Qdrant search for {query!r}")

    try:
        # Both the SentenceTransformer encode and the Qdrant client are blocking
        # CPU/IO calls. Awaiting them directly inside an async handler would stall
        # the event loop for the whole request, capping real concurrency at the
        # number of uvicorn workers. to_thread keeps the loop free.
        query_embedding = await asyncio.to_thread(
            get_embedding_engine().get_embedding, query
        )

        # Set up hybrid search filter if ticker is provided
        query_filter = None
        if ticker:
            query_filter = Filter(
                must=[
                    FieldCondition(
                        key="tickers",
                        match=MatchValue(value=ticker.upper())
                    )
                ]
            )

        # Search in Qdrant (using the updated API for qdrant-client 1.17+)
        search_response = await asyncio.to_thread(
            lambda: qdrant.query_points(
                collection_name=COLLECTION_NAME,
                query=query_embedding.tolist(),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            )
        )
        search_result = search_response.points

        # Format results (DaaS Contract)
        results = []
        for hit in search_result:
            results.append({
                "similarity_score": round(hit.score, 4),
                "title": hit.payload.get("title", "unknown"),
                "tickers": hit.payload.get("tickers", []),
                "sentiment_label": hit.payload.get("sentiment_label", "neutral")
            })

    except Exception as e:
        logger.error(f"Search failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal search engine error")

    await redis_client.set(cache_key, json.dumps(results), ex=SEARCH_CACHE_TTL_SECONDS)

    return results