"""
Ticker Backfill Script: re-extracts tickers with FlashText for Silver articles.

Reads title from Silver (Article) and description from Bronze (RawArticle
payload). Writes ONLY to Silver. Bronze remains immutable.

Two modes:

    # default: rescue articles that currently have no tickers at all
    docker compose exec api python -m app.scripts.backfill_tickers

    # re-extract for EVERY article, replacing what is stored
    docker compose exec api python -m app.scripts.backfill_tickers --all

`--all` exists because the default filter cannot repair a *wrong* attribution,
only a missing one. After INC-021 the stored tickers were not absent but
incorrect: "U.S." had been yielding U and S, "A colleague" yielding Agilent,
and those rows have non-empty arrays, so the default mode skips precisely the
ones that need fixing.

`--all` overwrites 58k rows. Take a database dump first.
"""
import asyncio
import logging
import sys

from sqlalchemy import select, func
from sqlalchemy.orm import joinedload

from app.db.session import AsyncSessionLocal
from app.models.article import Article
from app.models.raw_article import RawArticle  # noqa: F401  registers the mapper Article.raw_article points to
from app.services.ticker_extractor import TickerExtractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 200


async def run_backfill(process_all: bool = False):
    extractor = TickerExtractor()

    async with AsyncSessionLocal() as session:
        # joinedload fetches the Bronze row in the same query. The previous
        # version issued one SELECT per article, which is tolerable for a few
        # hundred orphans and not for a full pass over 58k rows.
        stmt = select(Article).options(joinedload(Article.raw_article))
        if not process_all:
            stmt = stmt.where(
                (Article.tickers == None) | (func.array_length(Article.tickers, 1) == None)  # noqa: E711
            )

        result = await session.execute(stmt)
        articles = result.unique().scalars().all()

        mode = "ALL articles (overwriting)" if process_all else "articles with no tickers"
        logger.info(f"Selected {len(articles)} Silver articles: mode: {mode}.")

        unchanged = changed = gained = cleared = 0
        for i, article in enumerate(articles):
            raw_article = article.raw_article
            if not raw_article:
                continue

            description = (raw_article.payload or {}).get("description", "") or ""
            found = extractor.extract(f"{article.title} {description}")

            before, after = set(article.tickers or []), set(found)
            if before == after:
                unchanged += 1
            else:
                changed += 1
                if not before:
                    gained += 1
                elif not after:
                    cleared += 1
                article.tickers = found

            if (i + 1) % BATCH_SIZE == 0:
                await session.commit()
                logger.info(
                    f"  {i + 1}/{len(articles)} processed | "
                    f"changed {changed} (gained {gained}, cleared {cleared})"
                )

        await session.commit()
        logger.info(
            f"Backfill complete. Processed {len(articles)} | unchanged {unchanged} | "
            f"changed {changed} | gained tickers {gained} | cleared to empty {cleared}"
        )


if __name__ == "__main__":
    asyncio.run(run_backfill(process_all="--all" in sys.argv))
