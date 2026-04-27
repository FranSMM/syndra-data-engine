from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, any_
from app.models.article import Article
from app.schemas.sentiment import ArticleSignalDTO


from sqlalchemy.orm import joinedload

import logging
logger = logging.getLogger(__name__)

async def fetch_recent_signals(db: AsyncSession, ticker: str, limit: int = 20, deduplicate: bool = True, dedup_window_hours: int = 3) -> list[ArticleSignalDTO]:
    """
    Fetches the latest processed articles for a given ticker from the Silver Layer.
    Uses native SQL column filtering instead of JSONB extraction.
    """
    ticker_upper = ticker.upper()

    # Direct column query on Silver Layer (orders of magnitude faster than JSONB)
    # Query more than requested to allow for deduplication
    stmt = (
        select(Article)
        .options(joinedload(Article.raw_article))
        .where(ticker_upper == any_(Article.tickers))
        .order_by(Article.published_at.desc().nullslast())
        .limit(limit * 2)
    )

    result = await db.execute(stmt)
    articles = result.scalars().all()

    from urllib.parse import urlparse
    import difflib

    signals = []
    # Store tuples of (title, sentiment_label, published_at) to prevent False Positives
    seen_articles = []
    
    # Observability metrics
    metrics = {
        "total_evaluated": len(articles),
        "discarded_duplicates": 0,
        "saved_by_sentiment": 0,
        "saved_by_temporal_evolution": 0
    }
    
    for article in articles:
        # Deduplication check: skip if title is >85% similar AND has the exact same sentiment AND within same temporal window
        is_duplicate = False
        duplicate_idx = -1
        
        # Only apply deduplication if deduplicate is True
        if deduplicate:
            for idx, (seen_title, seen_label, seen_time) in enumerate(seen_articles):
                if difflib.SequenceMatcher(None, article.title, seen_title).ratio() > 0.85:
                    if article.sentiment_label == seen_label:
                        # Check temporal distance
                        if article.published_at and seen_time:
                            time_diff = abs((article.published_at - seen_time).total_seconds())
                            if time_diff <= (dedup_window_hours * 3600):
                                is_duplicate = True
                                duplicate_idx = idx
                                break
                            else:
                                metrics["saved_by_temporal_evolution"] += 1
                        else:
                            is_duplicate = True
                            duplicate_idx = idx
                            break
                    else:
                        metrics["saved_by_sentiment"] += 1
                
        if is_duplicate:
            # Tie-breaker: If they have the exact same timestamp, prefer the longer, more informative title
            seen_time = seen_articles[duplicate_idx][2]
            seen_title = seen_articles[duplicate_idx][0]
            if article.published_at == seen_time and len(article.title) > len(seen_title):
                # We swap the DTO in place
                if article.raw_article and article.raw_article.url:
                    parsed_uri = urlparse(article.raw_article.url)
                    domain = parsed_uri.netloc.replace("www.", "")
                    source_name = domain.capitalize() if domain else "Unknown Source"
                    article_url = article.raw_article.url
                else:
                    source_name = article.source if article.source else "Unknown Source"
                    article_url = None
                
                signals[duplicate_idx] = ArticleSignalDTO(
                    title=article.title,
                    url=article_url,
                    published_at=article.published_at,
                    source=source_name,
                    sentiment_label=article.sentiment_label or "neutral",
                    sentiment_score=article.sentiment_score or 0.0,
                )
                seen_articles[duplicate_idx] = (article.title, article.sentiment_label, article.published_at)
            else:
                metrics["discarded_duplicates"] += 1
            continue
            
        seen_articles.append((article.title, article.sentiment_label, article.published_at))

        # Extract meaningful source domain from URL or fallback
        if article.raw_article and article.raw_article.url:
            parsed_uri = urlparse(article.raw_article.url)
            domain = parsed_uri.netloc.replace("www.", "")
            source_name = domain.capitalize() if domain else "Unknown Source"
            article_url = article.raw_article.url
        else:
            source_name = article.source if article.source else "Unknown Source"
            article_url = None
            
        signals.append(ArticleSignalDTO(
            title=article.title,
            url=article_url,
            published_at=article.published_at,
            source=source_name,
            sentiment_label=article.sentiment_label or "neutral",
            sentiment_score=article.sentiment_score or 0.0,
        ))

        # Stop once we have reached the original requested limit
        if len(signals) == limit:
            break

    logger.info(f"Deduplication Metrics for {ticker_upper} (Limit {limit}, Window {dedup_window_hours}h) | Evaluated: {metrics['total_evaluated']} | Discarded: {metrics['discarded_duplicates']} | Saved by Sentiment: {metrics['saved_by_sentiment']} | Saved by Time: {metrics['saved_by_temporal_evolution']}")
    
    return signals
