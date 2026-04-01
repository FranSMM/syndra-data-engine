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

# Singleton instance for the FastAPI app lifecycle
embedding_engine = EmbeddingService()