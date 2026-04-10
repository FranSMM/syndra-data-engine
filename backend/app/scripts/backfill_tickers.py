"""
Ticker Backfill Script — Re-extracts tickers using FlashText for Silver articles
that have empty tickers arrays (orphaned by the old regex method).

Reads title from Silver (Article) and description from Bronze (RawArticle payload).
Writes ONLY to Silver. Bronze remains immutable.

Usage:
    docker compose exec api python -m app.scripts.backfill_tickers
"""
import asyncio
import logging

from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from app.db.session import AsyncSessionLocal
from app.models.article import Article
from app.models.raw_article import RawArticle
from app.services.ticker_extractor import TickerExtractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 200


async def run_backfill():
    extractor = TickerExtractor()

    async with AsyncSessionLocal() as session:
        # Find Silver articles with empty or null tickers
        stmt = (
            select(Article)
            .where(
                (Article.tickers == None) | (func.array_length(Article.tickers, 1) == None)  # noqa: E711
            )
        )
        result = await session.execute(stmt)
        orphaned_articles = result.scalars().all()

        logger.info(f"Found {len(orphaned_articles)} orphaned Silver articles (no tickers).")

        rescued_count = 0
        for i, article in enumerate(orphaned_articles):
            # Load the Bronze record to get the description
            raw_stmt = select(RawArticle).where(RawArticle.id == article.raw_article_id)
            raw_result = await session.execute(raw_stmt)
            raw_article = raw_result.scalars().first()

            if not raw_article:
                continue

            description = raw_article.payload.get("description", "")
            text_to_scan = f"{article.title} {description}"

            found_tickers = extractor.extract(text_to_scan)

            if found_tickers:
                article.tickers = found_tickers
                rescued_count += 1

            # Commit in batches
            if (i + 1) % BATCH_SIZE == 0:
                await session.commit()
                logger.info(f"Committed batch... ({i + 1} processed, {rescued_count} rescued so far)")

        await session.commit()
        logger.info(
            f"Backfill complete. Processed: {len(orphaned_articles)} | "
            f"Rescued (now have tickers): {rescued_count}"
        )


if __name__ == "__main__":
    asyncio.run(run_backfill())
