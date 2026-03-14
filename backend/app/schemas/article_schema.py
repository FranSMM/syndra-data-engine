# Will contain Pydantic schema for Article data transfer
# This are the schemeas:

import hashlib
from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional

class FinancialMetadata(BaseModel):

    tickers: List[str] = Field(default_factory=list, description="List of financial tickers (e.g., ['AAPL', 'GOOGL'])")
    sentiment_score: Optional[float] = Field(default=None, description="Sentiment score from ML inference")
    sentiment_label: Optional[str] = Field(default=None, description="Sentiment label (e.g., 'Bullish', 'Bearish', 'Neutral')")
    

class ArticlePayload(BaseModel): 
    
    description: Optional[str] = Field(default=None, description="Article summary or snippet")
    
    # default_factory ensures this is always initialized even if the Spider doesn't provide it
    financial_metadata: FinancialMetadata = Field(default_factory=FinancialMetadata)

class ScrapedArticle(BaseModel):

    id: str = Field(..., description="SHA-256 hash of the URL")

    # HttpUrl ensures the URL is valid (starts with http:// or https://)
    url: HttpUrl

    # Article's title (is technically part of the payload, but we keep it here)
    title: str = Field(..., min_length=5)

    # Newspaper's identifies (e.g., 'el_pais')
    source: str = Field(..., description="Newspaper's identifier", min_length=2, max_length=100)

    published_at: datetime = Field(..., description="Article's publication timestamp")

    # Catch-all dictionary for everything else (author, full text, html tags, date)
    # This directly maps to JSONB column in Postgres
    payload: ArticlePayload = Field(default_factory=ArticlePayload)

    @classmethod
    def generate_id(cls, url: str) -> str: 
        """Generatees a reproducible SHA-256 hash for a given URL"""
        return hashlib.sha256(url.encode('utf-8')).hexdigest()