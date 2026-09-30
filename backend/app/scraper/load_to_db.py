import json
import asyncio
import logging
import sys
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import AsyncSessionLocal
from app.models import RawArticle

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def load_articles(file_path: str):
    """Reads the validated JSON and loads it into the raw_articles table."""
    try:
        with open(file_path, 'r') as f:
            articles_data = json.load(f)
    except FileNotFoundError:
        logger.error(f"File {file_path} not found. Did the spider run?")
        return
    
    async with AsyncSessionLocal() as session:
            inserted_count = 0

            for data in articles_data:
                # 1. Use the pre-calculated hash from Pydantic
                article_hash = data['id']

                # 2. Extract payload and inject top-level fields so they aren't lost
                article_payload = data.get('payload', {})
                article_payload['title'] = data.get('title')
                article_payload['published_at'] = data.get('published_at') # CRITICAL: Save the timestamp
                article_payload['source'] = data.get('source')

                # 3. INSERT ... ON CONFLICT DO NOTHING (silent idempotency, zero Postgres ERROR logs)
                stmt = pg_insert(RawArticle).values(
                    url=data['url'],
                    source=data['source'],
                    source_type=data.get('source_type', 'rss_feed'),
                    content_hash=article_hash,
                    payload=article_payload,
                ).on_conflict_do_nothing(index_elements=['content_hash'])

                result = await session.execute(stmt)

                if result.rowcount > 0:
                    inserted_count += 1
                    logger.info(f"Inserted: {data['title']}")

            await session.commit()
            duplicate_count = len(articles_data) - inserted_count
            logger.info(f"Load complete. Inserted: {inserted_count} | Duplicates skipped: {duplicate_count}")

from pathlib import Path

if __name__ == "__main__":
    # Accept file path as CLI argument (used by pipeline.py per-feed)
    # Fallback to default for backward compatibility with manual runs
    if len(sys.argv) > 1:
        output_path = Path(sys.argv[1])
    else:
        current_dir = Path(__file__).parent
        output_path = current_dir / "test_output.json"

    asyncio.run(load_articles(str(output_path)))