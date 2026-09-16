import logging
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.core.config import settings

logger = logging.getLogger(__name__)

qdrant = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

COLLECTION_NAME = settings.QDRANT_COLLECTION_NAME
VECTOR_SIZE = settings.QDRANT_VECTOR_SIZE

def init_qdrant_collection(): 
    """Idempotent initialization of the Qdrant collection and payload indexes."""
    try:
        collections = qdrant.get_collections().collections
        exists = any(c.name == COLLECTION_NAME for c in collections)

        if not exists:
            logger.info(f"Creating Qdrant collection: {COLLECTION_NAME}")
            qdrant.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config= models.VectorParams(
                    size=VECTOR_SIZE, 
                    distance=models.Distance.COSINE
                ),
            )
        else:
            logger.info(f"Qdrant collection {COLLECTION_NAME} already exists.")

        # Payload indexes for efficient pre-filtering in hybrid searches.
        # Idempotent: Qdrant silently skips if the index already exists.
        logger.info("Ensuring payload indexes exist...")

        # KEYWORD index on tickers array: enables exact match filtering (e.g. "AAPL")
        qdrant.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="tickers",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

        # KEYWORD index on sentiment_label: enables filtering by "positive"/"negative"/"neutral"
        qdrant.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="sentiment_label",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

        # DATETIME index on published_at: enables range queries (last 7 days, etc.)
        qdrant.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name="published_at",
            field_schema=models.PayloadSchemaType.DATETIME,
        )

        logger.info("Payload indexes ensured successfully.")

    except Exception as e:
        logger.error(f"Failed to initialize Qdrant collection: {str(e)}")
        raise