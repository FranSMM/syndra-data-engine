from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

# Engine setup. 'pool_pre_ping' verifies connections before using them.
engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    echo=False,           # Set to True only for local debugging
    future=True,          # Enforce SQLAlchemy 2.0 semantics
    pool_pre_ping=True,
    pool_size=5,          # Adjust based on expected concurrency
    max_overflow=10
)

# Session factory
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False # Critical for async operations
)

# FastAPI Dependency
async def get_db() -> AsyncSession: # type: ignore
    """
    Yields a database session and ensures it is closed after the request.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()