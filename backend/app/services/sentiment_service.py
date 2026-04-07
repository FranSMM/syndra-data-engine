from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.raw_article import RawArticle
from app.schemas.sentiment import ArticleSignalDTO
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import cast

async def fetch_recent_signals(db: AsyncSession, ticker: str, limit: int=20) -> list[ArticleSignalDTO]:
    """ 
    Fetches the latest processed articles for a given ticker utilizing the GIN index.
    """
    ticker_upper = ticker.upper()

    #SQLAlchemy syntax to leverage the GIN index on the JSONB array
    stmt = (
        select(RawArticle)
        .where(
            RawArticle.payload["financial_metadata"]["tickers"].cast(JSONB).contains(cast([ticker_upper], JSONB))
        )
        .order_by(RawArticle.id.desc())
        .limit(limit)
    )

    result = await db.execute(stmt)
    raw_articles = result.scalars().all()

    signals = []
    for article in raw_articles:
        meta = article.payload.get('financial_metadata', {})

        article_source= getattr(article, 'source', None) or article.payload.get('source')
        signals.append(ArticleSignalDTO(
            article_id=str(article.id),
            published_at=article.payload.get('published_at'),
            source=article_source,
            sentiment_label=meta.get('sentiment_label', 'neutral'),
            sentiment_score=meta.get('sentiment_score', 0.0),
        ))

    return signals
