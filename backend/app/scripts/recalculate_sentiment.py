"""
Script to recalculate sentiment score for all existing Silver articles
using the updated Quant Formula: (Positive - Negative) * (1 - Neutral).

Usage:
    docker compose exec backend python -m app.scripts.recalculate_sentiment
"""
import asyncio
import logging

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.raw_article import RawArticle
from app.models.article import Article
from app.services.sentiment_analyzer import FinancialSentimentAnalyzer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 200

async def run_sentiment_recalculation():
    logger.info("Starting historical sentiment recalculation from Bronze Layer...")
    
    analyzer = FinancialSentimentAnalyzer()
    
    async with AsyncSessionLocal() as session:
        # We will paginate using an offset to iterate over all existing Articles
        offset = 0
        
        while True:
            # Join Article with RawArticle to get the original text
            stmt = (
                select(Article, RawArticle)
                .join(RawArticle, Article.raw_article_id == RawArticle.id)
                .order_by(Article.id)
                .offset(offset)
                .limit(BATCH_SIZE)
            )
            result = await session.execute(stmt)
            batch = result.all()

            if not batch:
                logger.info(f"Finished evaluating all articles. Processed {offset} articles total.")
                break

            logger.info(f"Recalculating batch of {len(batch)} articles (Offset: {offset})...")
            
            for article, raw_article in batch:
                title = raw_article.payload.get('title') or ''
                description = raw_article.payload.get('description') or ''
                text_to_analyze = description or title
                
                sentiment_data = analyzer.analyze(text_to_analyze)
                
                if sentiment_data['sentiment_label'] is not None:
                    article.sentiment_label = sentiment_data['sentiment_label']
                    article.sentiment_score = sentiment_data['sentiment_score']
                    
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Failed to commit batch: {e}")
                break
                
            offset += BATCH_SIZE

if __name__ == "__main__":
    asyncio.run(run_sentiment_recalculation())
