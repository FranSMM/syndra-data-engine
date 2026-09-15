import asyncio
import logging

from sqlalchemy import select
from app.core.dates import normalise_published_at
from app.db.session import AsyncSessionLocal
from app.models.raw_article import RawArticle
from app.models.article import Article
from app.services.sentiment_analyzer import FinancialSentimentAnalyzer
from app.services.ticker_extractor import TickerExtractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Models will be lazy-loaded to save RAM and initialization time

async def run_sentiment_enrichment(batch_size: int = 200):
    async with AsyncSessionLocal() as session:
        while True:
            # Read pending articles from Bronze (immutable read)
            query = select(RawArticle).where(RawArticle.ingestion_state == "pending").limit(batch_size)
            result = await session.execute(query)
            articles = result.scalars().all()

            if not articles:
                logger.info("No more pending articles found for enrichment. Exiting cleanly.")
                break
                
            # LAZY LOADING: Only load the heavy ML models into RAM if there are articles to process
            logger.info("Initializing NLP models for inference...")
            analyzer = FinancialSentimentAnalyzer()
            ticker_extractor = TickerExtractor()
            
            logger.info(f"Processing batch of {len(articles)} articles...")
            processed_count = 0

            for raw_article in articles:

                # 1. Prepare text from Bronze payload (read-only access)
                title = raw_article.payload.get('title') or ''
                description = raw_article.payload.get('description') or ''
                text_to_analyze = description or title
                
                # 2. Run FinBERT inference
                sentiment_data = analyzer.analyze(text_to_analyze)
                
                # 3. Extract tickers via FlashText (Aho-Corasick)
                extracted_tickers = ticker_extractor.extract(f"{title} {description}")

                # 4. Skip if inference returned None
                if sentiment_data['sentiment_label'] is None:
                    logger.warning(f"Skipping article {raw_article.id} - inference returned None")
                    continue

                # 5. Parse published_at from Bronze payload.
                # Bronze keeps the feed's string untouched; this is where it
                # becomes the naive UTC value Silver holds. Passing created_at
                # lets the normaliser reject a date that cannot be true: the SEC
                # feed carries 1990s press releases stamped with the current
                # year, two of which claimed to be published months after we had
                # already read them.
                published_at_raw = raw_article.payload.get('published_at')
                published_at = normalise_published_at(
                    published_at_raw, ingested_at=raw_article.created_at
                )
                if published_at_raw and published_at is None:
                    # The article is still enriched and stored, but it will not
                    # appear in any time-window query. Silence here would make
                    # that look like an article we lost.
                    logger.warning(
                        f"Rejected published_at {published_at_raw!r} for article "
                        f"{raw_article.id} ({raw_article.source}): unparseable, or "
                        f"later than its own ingestion. Storing NULL."
                    )

                # 6. CREATE Silver record (instead of mutating Bronze payload)
                silver_article = Article(
                    raw_article_id=raw_article.id,
                    source=raw_article.source,
                    source_type=raw_article.source_type,
                    title=title or 'Unknown',
                    published_at=published_at,
                    sentiment_label=sentiment_data['sentiment_label'],
                    sentiment_score=sentiment_data['sentiment_score'],
                    tickers=extracted_tickers,
                )
                session.add(silver_article)

                # 7. Update ONLY the state flag in Bronze (the only allowed mutation)
                raw_article.ingestion_state = 'processed'
                processed_count += 1

            try:
                await session.commit()
                logger.info(f"Successfully enriched and committed {processed_count} articles to Silver Layer.")
            except Exception as e:
                await session.rollback()
                logger.error(f"Database commit failed during enrichment: {e}", exc_info=True)
                break
                
if __name__ == "__main__":
    asyncio.run(run_sentiment_enrichment(batch_size=200))
