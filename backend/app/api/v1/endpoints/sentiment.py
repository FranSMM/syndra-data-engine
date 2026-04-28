from fastapi import APIRouter, Depends, Query
from app.schemas.sentiment import TickerSentimentResponse
from app.services.sentiment_service import fetch_recent_signals
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from typing import Any

from app.api.deps import get_db, verify_api_key
from app.models.api_key import APIKey
from app.core.redis import redis_client
import json


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

router = APIRouter()


@router.get("/{ticker}", response_model=TickerSentimentResponse)
async def get_ticker_sentiment(
    ticker: str,
    limit: int = Query(default=20, ge=1, le=100, description="Number of recent articles to analyze"),
    deduplicate: bool = Query(default=True, description="Enable late deduplication"),
    dedup_window_hours: int = Query(default=3, ge=1, le=24, description="Time window for deduplication when enabled"),
    days_window: int | None = Query(default=None, ge=1, le=365, description="Number of days to look back for signals"),
    db: AsyncSession = Depends(get_db),
    client: APIKey = Depends(verify_api_key)
):
    """
    Get aggregated sentiment for a specific ticker.
    """

    # Internal log to know which client is making the request
    logger.info(f"API Request | Client: {client.client_name} | Ticker: {ticker.upper()}")
    
    # TRY IN REDIS (Response Cache Hit)
    # Cache sharing between clients is done using client_name in the cache key
    # example: cache_key = f"sentiment:{ticker.upper()}:{limit}"
    
    # Cache is scoped per-client to prevent cross-client data leakage.
    # Key includes deduplication settings and days_window to prevent serving mismatched results.
    cache_key = f"sentiment:{client.client_name}:{ticker.upper()}:{limit}:d{int(deduplicate)}:w{dedup_window_hours}:dw{days_window or 0}"
    cached_data = await redis_client.get(cache_key)
    if cached_data:
        logger.info(f"CACHE HIT: Served instantly from Redis ({ticker.upper()})")
        return json.loads(cached_data)

    logger.info(f"CACHE MISS: Computing in PostgreSQL for {ticker.upper()}")
    signals = await fetch_recent_signals(db, ticker, limit, deduplicate, dedup_window_hours, days_window)

    if not signals:
        return TickerSentimentResponse(
            ticker=ticker.upper(),
            time_window="N/A",
            aggregated_sentiment="neutral",
            average_score=0.0,
            article_count=0,
            recent_signals=[]
        )

    avg_score = sum(s.sentiment_score for s in signals) / len(signals)

    if avg_score > 0.15:
        agg_label = "positive"
    elif avg_score < -0.15:
        agg_label = "negative"
    else:
        agg_label = "neutral"
    
    # Calculate dynamic time window from the signals
    time_window = "unknown"
    if signals:
        dates = [s.published_at for s in signals if s.published_at]
        if dates:
            newest = max(dates)
            oldest = min(dates)
            delta = newest - oldest
            days = delta.days
            if days == 0:
                time_window = "24 hours"
            else:
                time_window = f"{days} days"

    response = TickerSentimentResponse(
        ticker=ticker.upper(),
        time_window=time_window,
        aggregated_sentiment=agg_label,
        average_score=round(avg_score, 4),
        article_count=len(signals),
        recent_signals=signals
    )

    # SAVE IN CACHE (Serialize the schema to JSON)
    await redis_client.set(cache_key, response.model_dump_json(), ex=300)
    
    return response