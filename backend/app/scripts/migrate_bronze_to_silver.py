"""
Bronze → Silver Migration Script (One-Off Backfill)

Rescues enrichment data (sentiment, tickers, published_at) that was
previously trapped inside the JSONB payload of RawArticle (Bronze)
and creates proper Silver Layer records in the Article table.

Idempotent: safe to re-run. Skips articles that already have a Silver record.

Usage:
    docker compose exec backend python -m app.scripts.migrate_bronze_to_silver
"""
import asyncio
import logging
from datetime import datetime

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.raw_article import RawArticle
from app.models.article import Article

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_migration(batch_size: int = 200):
    async with AsyncSessionLocal() as session:
        # Only migrate articles that were already enriched by FinBERT
        stmt = select(RawArticle).where(RawArticle.ingestion_state == "processed")
        result = await session.execute(stmt)
        raw_articles = result.scalars().all()

        logger.info(f"Found {len(raw_articles)} processed Bronze articles to migrate.")

        migrated_count = 0
        skipped_count = 0

        for raw in raw_articles:
            # Idempotency: skip if Silver record already exists
            check = await session.execute(
                select(Article.id).where(Article.raw_article_id == raw.id)
            )
            if check.scalars().first() is not None:
                skipped_count += 1
                continue

            payload = raw.payload or {}
            meta = payload.get("financial_metadata", {})

            # Parse published_at safely (it's a string inside JSONB)
            published_at_raw = payload.get("published_at")
            published_at = None
            if published_at_raw:
                try:
                    parsed = datetime.fromisoformat(published_at_raw)
                    # Strip timezone to match TIMESTAMP WITHOUT TIME ZONE column
                    published_at = parsed.replace(tzinfo=None)
                except (ValueError, TypeError):
                    logger.warning(f"Could not parse published_at for article {raw.id}: {published_at_raw}")

            silver_article = Article(
                raw_article_id=raw.id,
                title=payload.get("title", "Unknown"),
                published_at=published_at,
                sentiment_label=meta.get("sentiment_label"),
                sentiment_score=meta.get("sentiment_score"),
                tickers=meta.get("tickers", []),
            )
            session.add(silver_article)
            migrated_count += 1

            # Commit in batches to avoid memory bloat
            if migrated_count % batch_size == 0:
                await session.commit()
                logger.info(f"Committed batch... ({migrated_count} migrated so far)")

        await session.commit()
        logger.info(
            f"Migration complete. Migrated: {migrated_count} | Skipped (already exist): {skipped_count}"
        )


if __name__ == "__main__":
    asyncio.run(run_migration())
