"""
Vector backfill script — reads from Silver Layer (Article) instead of Bronze.
Generates embeddings with all-MiniLM-L6-v2 and upserts into Qdrant.

Usage:
    docker compose exec backend python -m app.backfill_vectors
"""
import asyncio
import logging
import uuid as uuid_lib

from sqlalchemy import select
from sqlalchemy import or_ as db_or
from qdrant_client.http.models import PointStruct

from app.db.session import AsyncSessionLocal
from app.models.article import Article
from app.models.raw_article import RawArticle
from app.db.vector_store import qdrant, init_qdrant_collection, COLLECTION_NAME
# embedding_engine is lazy-loaded inside run_backfill to save memory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 64


async def run_backfill():
    logger.info("Starting historical vector backfill from Silver Layer...")
    init_qdrant_collection()

    # LAZY LOADING: Only load the SentenceTransformer model if there's actual work
    model_loaded = False
    embedding_engine = None

    async with AsyncSessionLocal() as session:
        while True:
            # Query only UN-VECTORIZED articles (filter pushed to SQL, not Python)
            # Uses PostgreSQL JSONB operator to check the flag at DB level
            stmt = (
                select(Article, RawArticle)
                .join(RawArticle, Article.raw_article_id == RawArticle.id)
                .where(
                    Article.sentiment_label.is_not(None),
                    db_or(
                        RawArticle.payload["is_vectorized"].as_boolean().is_(None),
                        RawArticle.payload["is_vectorized"].as_boolean() == False,
                    )
                )
                .limit(BATCH_SIZE)
            )
            result = await session.execute(stmt)
            batch = result.all()

            if not batch:
                if not model_loaded:
                    logger.info("Found 0 Silver articles to index. Exiting cleanly.")
                break

            if not model_loaded:
                from app.services.embedding_service import embedding_engine as _engine
                embedding_engine = _engine
                model_loaded = True
                logger.info(f"Found articles to index. Model loaded.")

            texts_to_encode = []
            points = []

            for article, raw in batch:
                desc = raw.payload.get("description", "")
                texts_to_encode.append(f"{article.title}\n{desc}")

            logger.info(f"Encoding batch of {len(batch)} articles...")
            embeddings = embedding_engine.get_embeddings_batch(texts_to_encode)

            for (article, raw), embedding in zip(batch, embeddings):
                # Deterministic UUID based on URL (idempotency)
                embedding_id = str(uuid_lib.uuid5(uuid_lib.NAMESPACE_DNS, raw.url))

                payload = {
                    "article_id": str(article.id),
                    "tickers": article.tickers or [],
                    "title": article.title,
                    "sentiment_label": article.sentiment_label,
                    "published_at": article.published_at.isoformat() if article.published_at else None,
                }

                points.append(
                    PointStruct(
                        id=embedding_id,
                        vector=embedding,
                        payload=payload,
                    )
                )

            # Upsert into Qdrant
            qdrant.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
                wait=True,
            )

            # Mark as vectorized in Bronze payload (the only allowed flag update)
            for article, raw in batch:
                updated_payload = dict(raw.payload)
                updated_payload["is_vectorized"] = True
                raw.payload = updated_payload
                session.add(raw)

            await session.commit()
            logger.info(f"Successfully upserted {len(points)} points to Qdrant.")

    logger.info("Backfill completed successfully.")


if __name__ == "__main__":
    asyncio.run(run_backfill())