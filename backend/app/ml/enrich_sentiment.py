import asyncio
import logging
from datetime import datetime

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.raw_article import RawArticle
from app.models.article import Article
from app.services.sentiment_analyzer import FinancialSentimentAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Initialize the analyzer once (singleton pattern)
analyzer = FinancialSentimentAnalyzer()

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
            
            logger.info(f"Processing batch of {len(articles)} articles...")
            processed_count = 0

            for raw_article in articles:

                # 1. Prepare text from Bronze payload (read-only access)
                title = raw_article.payload.get('title') or ''
                description = raw_article.payload.get('description') or ''
                text_to_analyze = description or title
                
                # 2. Run FinBERT inference
                sentiment_data = analyzer.analyze(text_to_analyze)
                
                # 3. Extract tickers
                extracted_tickers = analyzer.extract_tickers(title, description)

                # 4. Skip if inference returned None
                if sentiment_data['sentiment_label'] is None:
                    logger.warning(f"Skipping article {raw_article.id} - inference returned None")
                    continue

                # 5. Parse published_at from Bronze payload
                published_at_raw = raw_article.payload.get('published_at')
                published_at = None
                if published_at_raw:
                    try:
                        published_at = datetime.fromisoformat(published_at_raw)
                    except (ValueError, TypeError):
                        logger.warning(f"Could not parse published_at for article {raw_article.id}")

                # 6. CREATE Silver record (instead of mutating Bronze payload)
                silver_article = Article(
                    raw_article_id=raw_article.id,
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
