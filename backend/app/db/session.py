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

# NOTE: the FastAPI request-scoped dependency lives in app/api/deps.py::get_db.
# A second, slightly different copy used to sit here and was never imported by
# anything — two definitions of the same dependency is an invitation to drift.
# This module owns the engine and the session factory only; the ETL scripts and
# the API both build on AsyncSessionLocal directly.