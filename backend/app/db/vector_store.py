import logging
from qdrant_client import QdrantClient
from qdrant_client.http import models
from app.core.config import settings

logger = logging.getLogger(__name__)

qdrant = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)

COLLECTION_NAME = settings.QDRANT_COLLECTION_NAME
VECTOR_SIZE = settings.QDRANT_VECTOR_SIZE

def init_qdrant_collection(): 
    """Idempotent initialization of the Qdrant collection."""
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

    except Exception as e:
        logger.error(f"Failed to initialize Qdrant collection: {str(e)}")
        raise