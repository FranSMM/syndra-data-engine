from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import ForeignKey, String, Float, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.raw_article import RawArticle


class Article(Base):
    """
    Silver Layer: Enriched, structured article data.
    Produced by the ML pipeline (FinBERT + ticker extraction).
    This table is the Single Source of Truth for the API layer.

    Immutability contract: RawArticle (Bronze) is NEVER mutated after insert.
    All enrichment output lives here.
    """
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # 1:1 with Bronze. unique=True enforces idempotency at DB level.
    raw_article_id: Mapped[int] = mapped_column(
        ForeignKey("raw_articles.id"), unique=True, index=True, nullable=False
    )

    # Core article metadata (propagated from Bronze to avoid JOINs in API)
    source: Mapped[str] = mapped_column(String, index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    # Core article data (extracted from Bronze payload)
    title: Mapped[str] = mapped_column(String, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(index=True, nullable=True)

    # NLP enrichment (FinBERT output)
    sentiment_label: Mapped[Optional[str]] = mapped_column(String(20), index=True, nullable=True)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Extracted tickers (Regex now, FlashText later)
    tickers: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)

    # Audit
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    # Relationship back to Bronze for full payload access when needed
    raw_article: Mapped["RawArticle"] = relationship("RawArticle", back_populates="article")
