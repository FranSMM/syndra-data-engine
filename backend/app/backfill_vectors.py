import asyncio
import logging
import uuid
from sqlalchemy import select, or_
from qdrant_client.http.models import PointStruct

from app.db.session import AsyncSessionLocal
from app.models.raw_article import RawArticle
from app.db.vector_store import qdrant, init_qdrant_collection, COLLECTION_NAME
from app.services.embedding_service import embedding_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BATCH_SIZE = 64

async def run_backfill():
    logger.info("Starting historical vector backfill...")
    init_qdrant_collection()

    async with AsyncSessionLocal() as session:
        # Fetch all articles that don't have vectors yet
        # B2B Data contract: Only index clean, enriched data
        stmt = select(RawArticle).where(
            RawArticle.ingestion_state == 'processed',
            or_(
                # .op('->>') is used to extract a JSON field as text
                RawArticle.payload.op('->>')('is_vectorized') == None,
                RawArticle.payload.op('->>')('is_vectorized') == 'false'
            )
        )
        result = await session.execute(stmt)
        articles = result.scalars().all()

        logger.info(f"Found {len(articles)} processed articles to index.")

        # Process in batches
        for i in range(0, len(articles), BATCH_SIZE):
            batch = articles[i:i + BATCH_SIZE]
            texts_to_encode = []
            points = []

            for article in batch:
                title = article.payload.get("title", "")
                desc = article.payload.get("description", "")
                texts_to_encode.append(f"{title}\n{desc}")
            
            logger.info(f"Encoding batch {i//BATCH_SIZE + 1}...")
            embeddings = embedding_engine.get_embeddings_batch(texts_to_encode)

            # Prepare points for Qdrant
            points = []
            for article, embedding in zip(batch, embeddings):
                # Deterministic UUID based on Postgres ID (idempotency)
                embedding_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, article.url))

                title = article.payload.get("title", "Unknown")

                payload = {
                    "article_id": str(article.id),
                    "tickers": article.payload.get("financial_metadata", {}).get("tickers", []),
                    "title": title,
                    "sentiment_label": article.payload.get("financial_metadata", {}).get("sentiment_label", "neutral"),
                    "published_at": article.payload.get("published_at")
                }

                points.append(
                    PointStruct(
                        id=embedding_id,
                        vector=embedding,
                        payload=payload
                    )
                )
            
            # Upsert into Qdrant
            qdrant.upsert(
                collection_name=COLLECTION_NAME,
                points=points,
                wait=True
            )

            # Update PostgreSQL payload flag after successful vectorization
            for article in batch:
                article_payload = dict(article.payload)
                article_payload["is_vectorized"] = True
                article.payload = article_payload
                session.add(article)

            await session.commit()

            logger.info(f"Successfully upserted {len(points)} points to Qdrant and marked as vectorized in DB.")

    logger.info("Backfill completed successfully.")

if __name__ == "__main__":
    asyncio.run(run_backfill())