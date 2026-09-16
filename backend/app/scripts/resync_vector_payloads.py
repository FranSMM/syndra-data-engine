"""
Re-sync Qdrant payloads with the Silver Layer.

`backfill_vectors` is incremental by design: it skips anything already flagged
`is_vectorized`, so it cannot repair a point whose payload has gone stale. After
the ticker extraction was corrected (INC-021) the two stores disagreed:
Postgres had 0 articles tagged `AI`, Qdrant still had 1,145, which meant
/sentiment/{ticker} and /search/semantic?ticker= returned contradictory answers
for the same symbol.

Only the payload is rewritten. The vectors are embeddings of the title and
description, neither of which changed, so re-encoding 60k articles on CPU would
cost hours and produce identical vectors.

Point IDs are recomputed the same way backfill_vectors derives them:
uuid5(NAMESPACE_DNS, raw_article.url), so this stays in step with it.

Usage:
    docker compose exec api python -m app.scripts.resync_vector_payloads
    docker compose exec api python -m app.scripts.resync_vector_payloads --dry-run
"""
import asyncio
import logging
import sys
import uuid as uuid_lib
from collections import defaultdict

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.article import Article
from app.models.raw_article import RawArticle
from app.db.vector_store import qdrant, COLLECTION_NAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Qdrant applies one payload to a list of point IDs per call, so articles are
# grouped by their ticker set. Most share one: the empty set alone covers
# roughly half the corpus, which turns ~60k calls into a few thousand.
MAX_IDS_PER_CALL = 500


async def run_resync(dry_run: bool = False):
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Article.tickers, RawArticle.url)
            .join(RawArticle, Article.raw_article_id == RawArticle.id)
        )
        rows = (await session.execute(stmt)).all()
        logger.info(f"Read {len(rows)} Silver articles.")

    by_tickers: dict[tuple, list[str]] = defaultdict(list)
    for tickers, url in rows:
        key = tuple(sorted(tickers or []))
        by_tickers[key].append(str(uuid_lib.uuid5(uuid_lib.NAMESPACE_DNS, url)))

    logger.info(f"Grouped into {len(by_tickers)} distinct ticker sets.")

    if dry_run:
        top = sorted(by_tickers.items(), key=lambda kv: -len(kv[1]))[:8]
        for key, ids in top:
            logger.info(f"  {len(ids):>6} points -> {list(key)[:6]}")
        logger.info("Dry run: nothing written.")
        return

    calls = points = 0
    for key, ids in by_tickers.items():
        payload = {"tickers": list(key)}
        for i in range(0, len(ids), MAX_IDS_PER_CALL):
            chunk = ids[i:i + MAX_IDS_PER_CALL]
            qdrant.set_payload(
                collection_name=COLLECTION_NAME,
                payload=payload,
                points=chunk,
                wait=False,          # fire-and-forget; a final wait=True follows
            )
            calls += 1
            points += len(chunk)
            if calls % 200 == 0:
                logger.info(f"  {points} points updated across {calls} calls...")

    # One blocking call at the end so the function does not return before Qdrant
    # has applied the queued updates.
    qdrant.set_payload(
        collection_name=COLLECTION_NAME,
        payload={"tickers": list(next(iter(by_tickers)))},
        points=by_tickers[next(iter(by_tickers))][:1],
        wait=True,
    )
    logger.info(f"Re-sync complete. {points} point payloads updated in {calls} calls.")


if __name__ == "__main__":
    asyncio.run(run_resync(dry_run="--dry-run" in sys.argv))
