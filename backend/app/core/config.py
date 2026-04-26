from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, computed_field
from pydantic_core import MultiHostUrl

class Settings(BaseSettings):
    PROJECT_NAME: str = "Syndra"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # "production" disables Swagger UI

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore"
    )
    
    # Base de datos (Postgres)
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    # We set a default 'localhost' here so local execution outside Docker works without modifying the .env file.
    # When running inside Docker, the .env file will override this with 'db'.
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: str = "5432"
    POSTGRES_DB: str

    # Pydantic Fail-Fast validation for the DB URL
    @computed_field
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> str:
        # Note the use of postgresql+asyncpg driver
        return MultiHostUrl.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=int(self.POSTGRES_PORT),
            path=self.POSTGRES_DB,
        ).unicode_string()

    # Base de datos vectorial (Qdrant)
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "financial_signals"
    QDRANT_VECTOR_SIZE: int = 384

    @computed_field
    @property
    def QDRANT_URL(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

    # Embedding Model Configuration
    EMBEDDING_MODEL_NAME: str = "all-MiniLM-L6-v2"

settings = Settings()