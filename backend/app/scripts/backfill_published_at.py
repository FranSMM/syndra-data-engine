"""
Publication Date Backfill: re-derives Silver's published_at from Bronze.

Reads the untouched feed string from Bronze (RawArticle payload) and rewrites
Silver (Article.published_at) through app.core.dates.normalise_published_at.
Writes ONLY to Silver. Bronze remains immutable.

    # show what would change, touch nothing
    docker exec syndra_api python -m app.scripts.backfill_published_at --dry-run

    # apply
    docker exec syndra_api python -m app.scripts.backfill_published_at

Why this exists. Until 15/09/2026 the enrichment discarded the timezone offset
instead of converting it: a feed saying "07:00:00-05:00" was stored as 07:00
rather than 12:00. Feeds emitting Z were unaffected, which is why this went
unseen: 69,962 of 70,001 articles came from two UTC feeds and were always
right. The 39 SEC articles carry -05:00 and sat five hours early, wider than
the 3h window the deduplicator compares timestamps against.

The same pass applies the plausibility guard, so articles the SEC's feed dated
after we ingested them end up with NULL rather than a date months in the future.

Two properties worth preserving if this is ever edited.

**Idempotent.** It recomputes from Bronze rather than adjusting Silver in place,
so a second run changes nothing. An "add five hours" migration run twice would
silently shift everything by ten.

**Bounded memory.** It pages by primary key and pulls only the four values it
needs, extracting the one payload key server-side. Loading ORM objects would
drag 70k JSONB payloads through a container capped at 1.25G to read one string
out of each.
"""
import argparse
import asyncio
import logging

from sqlalchemy import select, update

from app.core.dates import normalise_published_at
from app.core.source_rules import has_implausible_publication_year
from app.db.session import AsyncSessionLocal
from app.models.article import Article
from app.models.raw_article import RawArticle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


def _page_query(after_id: int):
    """
    Keyset pagination, not OFFSET: OFFSET re-scans everything it skips, so the
    last page of a 70k table costs 70k rows to produce.
    """
    return (
        select(
            Article.id,
            Article.source,
            Article.published_at,
            RawArticle.url,
            RawArticle.payload["published_at"].astext.label("raw_published_at"),
            RawArticle.created_at.label("ingested_at"),
        )
        .join(RawArticle, RawArticle.id == Article.raw_article_id)
        .where(Article.id > after_id)
        .order_by(Article.id)
        .limit(BATCH_SIZE)
    )


async def backfill(dry_run: bool = False) -> None:
    changed = nulled = unchanged = scanned = 0
    after_id = 0

    async with AsyncSessionLocal() as session:
        while True:
            rows = (await session.execute(_page_query(after_id))).all()
            if not rows:
                break

            for row in rows:
                scanned += 1
                after_id = row.id

                corrected = normalise_published_at(
                    row.raw_published_at, ingested_at=row.ingested_at
                )
                # Same two rules the enrichment applies, in the same order, so a
                # backfilled row is indistinguishable from a freshly enriched
                # one. Two copies of this logic drifting apart would be worse
                # than the bug being fixed.
                if has_implausible_publication_year(row.source, row.url, corrected):
                    corrected = None

                if corrected == row.published_at:
                    unchanged += 1
                    continue

                if corrected is None:
                    nulled += 1
                    logger.info(
                        "id=%s: %s -> NULL (feed said %r, ingested %s)",
                        row.id, row.published_at, row.raw_published_at, row.ingested_at,
                    )
                else:
                    changed += 1
                    logger.info("id=%s: %s -> %s", row.id, row.published_at, corrected)

                if not dry_run:
                    await session.execute(
                        update(Article)
                        .where(Article.id == row.id)
                        .values(published_at=corrected)
                    )

            if not dry_run:
                await session.commit()

    verb = "would change" if dry_run else "changed"
    logger.info(
        "Scanned %d. %s %d timestamps, %s %d to NULL, left %d untouched.",
        scanned, verb, changed, verb, nulled, unchanged,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-derive Silver published_at from Bronze.")
    parser.add_argument("--dry-run", action="store_true", help="report changes without writing")
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run))
