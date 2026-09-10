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


# --- Prefect's database, read-only ------------------------------------------
# Used by app/core/metrics.py to derive the ETL stage durations that Prefect
# already records. Nothing here ever writes to it: it belongs to the Prefect
# server, and a second writer to someone else's schema is how migrations start
# failing in ways nobody can explain.
#
# The pool is deliberately tiny. This engine answers two aggregate queries a
# minute for a single scrape endpoint, so at most two connections; sizing it
# like the API's pool would mean reserving Postgres connections that sit idle
# and compete with the ones actually serving requests.
prefect_engine = create_async_engine(
    settings.PREFECT_DATABASE_URI,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_size=1,
    max_overflow=1,
)

PrefectSessionLocal = async_sessionmaker(
    bind=prefect_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

# NOTE: the FastAPI request-scoped dependency lives in app/api/deps.py::get_db.
# A second, slightly different copy used to sit here and was never imported by
# anything — two definitions of the same dependency is an invitation to drift.
# This module owns the engine and the session factory only; the ETL scripts and
# the API both build on AsyncSessionLocal directly.