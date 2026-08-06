from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, any_
from app.models.article import Article
from app.schemas.sentiment import ArticleSignalDTO

from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta, timezone

import logging
logger = logging.getLogger(__name__)

# Deduplication discards rows, so we over-fetch to still have a chance of
# filling `limit`. This is a heuristic, not a guarantee: a ticker whose feed is
# mostly reprints can still return fewer than `limit` signals, which is why the
# short-result case is logged explicitly below instead of passing unnoticed.
DEDUP_OVERFETCH_FACTOR = 2


async def fetch_recent_signals(db: AsyncSession, ticker: str, limit: int = 20, deduplicate: bool = True, dedup_window_hours: int = 3, days_window: int | None = None) -> list[ArticleSignalDTO]:
    """
    Fetches the latest processed articles for a given ticker from the Silver Layer.
    Optionally filters by days_window. Uses native SQL column filtering instead of JSONB extraction.
    """
    ticker_upper = ticker.upper()

    # Direct column query on Silver Layer (orders of magnitude faster than JSONB)
    # Query more than requested to allow for deduplication
    stmt = (
        select(Article)
        .options(joinedload(Article.raw_article))
        .where(ticker_upper == any_(Article.tickers))
    )

    if days_window is not None:
        # Article.published_at is stored as a naive UTC timestamp (the enrichment
        # pipeline strips tzinfo), so the cutoff must be naive UTC too. Built from
        # an explicitly aware "now" because datetime.utcnow() is deprecated in 3.12+.
        cutoff_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_window)
        stmt = stmt.where(Article.published_at >= cutoff_date)

    fetch_size = limit * DEDUP_OVERFETCH_FACTOR if deduplicate else limit
    stmt = (
        stmt.order_by(Article.published_at.desc().nullslast())
        .limit(fetch_size)
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
            # Why a single reason per article instead of counting inside the loop:
            # one article is compared against every previously kept article, so a
            # headline near-matching three earlier ones used to add three counts to
            # the metric. The article was still kept exactly once. We record the
            # first reason it survived and count it once, after the scan.
            saved_reason = None

            for idx, (seen_title, seen_label, seen_time) in enumerate(seen_articles):
                if difflib.SequenceMatcher(None, article.title, seen_title).ratio() <= 0.85:
                    continue

                # Near-identical headline with the opposite sentiment is a genuine
                # contrary signal, not a reprint. ML safety net (ADR 033).
                if article.sentiment_label != seen_label:
                    saved_reason = saved_reason or "saved_by_sentiment"
                    continue

                if article.published_at and seen_time:
                    time_diff = abs((article.published_at - seen_time).total_seconds())
                    if time_diff <= (dedup_window_hours * 3600):
                        is_duplicate = True
                        duplicate_idx = idx
                        break
                    # Same story, same sentiment, but far enough apart in time to
                    # be a genuine follow-up rather than a reprint.
                    saved_reason = saved_reason or "saved_by_temporal_evolution"
                    continue

                # No usable timestamps on either side: fall back to treating the
                # title+sentiment match as a duplicate.
                is_duplicate = True
                duplicate_idx = idx
                break

            if not is_duplicate and saved_reason:
                metrics[saved_reason] += 1


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

    # A short result set has two very different causes and the client cannot tell
    # them apart from the response alone: either the Silver Layer genuinely holds
    # fewer articles for this ticker, or deduplication ate into the over-fetch
    # budget. Surface the difference so it shows up in the logs instead of looking
    # like thin coverage.
    if len(signals) < limit:
        if metrics["total_evaluated"] < fetch_size:
            logger.info(
                f"Short result for {ticker_upper}: {len(signals)}/{limit} signals — "
                f"Silver Layer only holds {metrics['total_evaluated']} matching articles."
            )
        else:
            logger.warning(
                f"Short result for {ticker_upper}: {len(signals)}/{limit} signals after "
                f"deduplicating {metrics['total_evaluated']} fetched articles. "
                f"Consider raising DEDUP_OVERFETCH_FACTOR (currently {DEDUP_OVERFETCH_FACTOR})."
            )

    return signals
