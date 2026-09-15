"""
Publication Date Backfill — re-derives Silver's published_at from Bronze.

Reads the untouched feed string from Bronze (RawArticle payload) and rewrites
Silver (Article.published_at) through app.core.dates.normalise_published_at.
Writes ONLY to Silver. Bronze remains immutable.

    # show what would change, touch nothing
    docker compose exec api python -m app.scripts.backfill_published_at --dry-run

    # apply
    docker compose exec api python -m app.scripts.backfill_published_at

Why this exists. Until 15/09/2026 the enrichment discarded the timezone offset
instead of converting it: a feed saying "07:00:00-05:00" was stored as 07:00
rather than 12:00. Feeds emitting Z were unaffected, which is why this went
unseen — 69,962 of 70,001 articles came from two UTC feeds and were always
right. The 39 SEC articles carry -05:00 and sat five hours early, wider than
the 3h window the deduplicator compares timestamps against.

The same pass applies the plausibility guard, so articles the SEC's feed dated
after we ingested them end up with NULL rather than a date three months in the
future.

Idempotent: it recomputes from Bronze rather than adjusting Silver in place, so
running it twice changes nothing the second time. That matters — an "add five
hours" migration run twice would silently shift everything ten.
"""
import argparse
import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.core.dates import normalise_published_at
from app.db.session import AsyncSessionLocal
from app.models.article import Article
from app.models.raw_article import RawArticle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 500


async def backfill(dry_run: bool = False) -> None:
    changed = nulled = unchanged = 0

    async with AsyncSessionLocal() as session:
        stmt = (
            select(Article)
            .options(joinedload(Article.raw_article))
            .order_by(Article.id)
            .execution_options(yield_per=BATCH_SIZE)
        )
        result = await session.stream(stmt)

        async for article in (await result.scalars()).partitions(BATCH_SIZE):
            for row in article:
                raw = row.raw_article.payload.get("published_at") if row.raw_article else None
                corrected = normalise_published_at(
                    raw, ingested_at=row.raw_article.created_at if row.raw_article else None
                )

                if corrected == row.published_at:
                    unchanged += 1
                    continue

                if corrected is None:
                    nulled += 1
                    logger.info(
                        "id=%s %s: %s -> NULL (feed said %r, ingested %s)",
                        row.id, row.source, row.published_at, raw,
                        row.raw_article.created_at if row.raw_article else "?",
                    )
                else:
                    changed += 1
                    logger.info(
                        "id=%s %s: %s -> %s", row.id, row.source, row.published_at, corrected
                    )

                if not dry_run:
                    row.published_at = corrected

            if not dry_run:
                await session.commit()

    verb = "would change" if dry_run else "changed"
    logger.info(
        "Done. %s %d timestamps, %s %d to NULL, left %d untouched.",
        verb, changed, verb, nulled, unchanged,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="report changes without writing"
    )
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run))
