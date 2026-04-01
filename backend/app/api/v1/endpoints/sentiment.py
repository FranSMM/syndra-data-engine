from fastapi import APIRouter, Depends, Query
from app.schemas.sentiment import TickerSentimentResponse
from app.services.sentiment_service import fetch_recent_signals
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db

router = APIRouter()

@router.get("/{ticker}", response_model=TickerSentimentResponse)
async def get_ticker_sentiment(
    ticker: str,
    limit: int = Query(default=20, ge=1, le=100, description="Number of recent articles to analyze"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get aggregated sentiment for a specific ticker.
    """
    
    signals = await fetch_recent_signals(db, ticker, limit)

    if not signals:
        return TickerSentimentResponse(
            ticker=ticker.upper(),
            aggregated_sentiment="neutral",
            average_score=0.0,
            article_count=0,
            recent_signals=[]
        )

    avg_score = sum(s.sentiment_score for s in signals) / len(signals)

    if avg_score > 0.15:
        agg_label = "bullish"
    elif avg_score < -0.15:
        agg_label = "bearish"
    else:
        agg_label = "neutral"
    
    return TickerSentimentResponse(
        ticker=ticker.upper(),
        aggregated_sentiment=agg_label,
        average_score=round(avg_score, 4),
        article_count=len(signals),
        recent_signals=signals
    )