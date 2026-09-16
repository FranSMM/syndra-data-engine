from sentence_transformers import SentenceTransformer
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class EmbeddingService:
    def __init__(self):
        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL_NAME} on CPU to prevent GPU memory leaks")

        # Load the pre-trained model
        self.model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME, device='cpu')

    def get_embedding(self, text: str) -> list[float]:
        """Generate embedding for a given text."""
        try:
            embedding = self.model.encode(text)
            logger.info(f"Generated embedding for text: {text}")
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding for text: {text}")
            raise

    def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts."""
        try:
            embeddings = self.model.encode(texts, convert_to_numpy=True)
            logger.info(f"Generated embeddings for {len(texts)} texts")
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"Failed to generate embeddings for batch of texts")
            raise

# Lazy-loaded singleton: model is NOT loaded at import time.
# This prevents the API from eagerly loading ~90MB of weights on every
# startup / hot-reload. The model is only loaded on first actual use.
_embedding_engine: EmbeddingService | None = None

def get_embedding_engine() -> EmbeddingService:
    """Return the singleton EmbeddingService, creating it on first call."""
    global _embedding_engine
    if _embedding_engine is None:
        _embedding_engine = EmbeddingService()
    return _embedding_engine