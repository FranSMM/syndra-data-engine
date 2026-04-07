import asyncio
import logging
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from app.db.session import AsyncSessionLocal
from app.models.raw_article import RawArticle
from app.services.sentiment_analyzer import FinancialSentimentAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Initialize the analyzer once (singleton pattern)
analyzer = FinancialSentimentAnalyzer()

async def run_sentiment_enrichment(batch_size: int = 200):
    async with AsyncSessionLocal() as session:
        while True:
            # FIX: State was erroneously set to "loaded", project context mandates "pending"
            query = select(RawArticle).where(RawArticle.ingestion_state == "pending").limit(batch_size)
            result = await session.execute(query)

            # .scalars() returns the first element of each row (the RawArticle object)
            articles = result.scalars().all()

            if not articles:
                logger.info("No more pending articles found for enrichment. Exiting cleanly.")
                break
            
            logger.info(f"Processing batch of {len(articles)} articles...")
            processed_count = 0

            for article in articles:

                # 1. Prepare text
                title = article.payload.get('title') or ''
                description = article.payload.get('description') or ''
                text_to_analyze = description or title
                
                # 2. Analyze sentiment
                sentiment_data = analyzer.analyze(text_to_analyze)
                
                # 3. Extract tickers
                extracted_tickers = analyzer.extract_tickers(title, description)

                # 4. Update article with sentiment data
                if sentiment_data['sentiment_label'] is None:
                    logger.warning(f"Skipping article {article.id} - inference returned None")
                    continue

                if 'financial_metadata' not in article.payload:
                    article.payload['financial_metadata'] = {}

                # Update the payload
                article.payload['financial_metadata']['sentiment_label'] = sentiment_data['sentiment_label']
                article.payload['financial_metadata']['sentiment_score'] = sentiment_data['sentiment_score']
                article.payload['financial_metadata']['tickers'] = extracted_tickers

                # Mark the payload as modified
                flag_modified(article, "payload")
                article.ingestion_state = 'processed'
                processed_count += 1

            try:
                await session.commit()
                logger.info(f"Successfully enriched and committed {processed_count} articles.")
            except Exception as e:
                await session.rollback()
                logger.error(f"Database commit failed during enrichment: {e}", exc_info=True)
                break
                
if __name__ == "__main__":
    asyncio.run(run_sentiment_enrichment(batch_size=200))
