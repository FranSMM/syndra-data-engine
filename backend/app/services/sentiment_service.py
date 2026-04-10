from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, any_
from app.models.article import Article
from app.schemas.sentiment import ArticleSignalDTO


async def fetch_recent_signals(db: AsyncSession, ticker: str, limit: int = 20) -> list[ArticleSignalDTO]:
    """
    Fetches the latest processed articles for a given ticker from the Silver Layer.
    Uses native SQL column filtering instead of JSONB extraction.
    """
    ticker_upper = ticker.upper()

    # Direct column query on Silver Layer (orders of magnitude faster than JSONB)
    stmt = (
        select(Article)
        .where(ticker_upper == any_(Article.tickers))
        .order_by(Article.published_at.desc().nullslast())
        .limit(limit)
    )

    result = await db.execute(stmt)
    articles = result.scalars().all()

    signals = []
    for article in articles:
        signals.append(ArticleSignalDTO(
            article_id=str(article.id),
            published_at=article.published_at,
            source=None,  # Source lives in Bronze; join if needed later
            sentiment_label=article.sentiment_label or "neutral",
            sentiment_score=article.sentiment_score or 0.0,
        ))

    return signals
