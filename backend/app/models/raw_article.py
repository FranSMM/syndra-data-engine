from datetime import datetime
from typing import Any

from sqlalchemy import String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class RawArticle(Base):
    __tablename__ = "raw_articles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    url: Mapped[str] = mapped_column(String, index=True, nullable=False)
    source: Mapped[str] = mapped_column(String, index=True, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ingestion_state: Mapped[str] = mapped_column(String(20), server_default="pending", nullable=False) # pending, processed, failed
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    article: Mapped["Article"] = relationship("Article", back_populates="raw_article", uselist=False)
