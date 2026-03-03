from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    raw_article_id: Mapped[int] = mapped_column(ForeignKey("raw_articles.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String, index=True, nullable=False)
    content_cleaned: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)

    raw_article: Mapped["RawArticle"] = relationship("RawArticle", back_populates="articles")
