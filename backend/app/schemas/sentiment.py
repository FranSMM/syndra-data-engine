from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from typing import List, Optional

class ArticleSignalDTO(BaseModel):
    """Represents a single processed article signal."""
    title: str = Field(..., description="Headline of the article")
    url: Optional[str] = Field(None, description="Original source URL")
    published_at: Optional[datetime] = Field(None, description="ISO 8601 publication timestamp")
    source: Optional[str] = Field(None, description="Origin of the news (e.g., Yahoo Finance)")
    sentiment_label: str = Field(..., description="Classification: positive, negative, neutral")
    sentiment_score: float = Field(..., ge=-1.0, le=1.0, description="Confidence score from -1.0 to 1.0")

    # Allow ORM attributes to be mapped directly to Pydantic fields
    model_config = ConfigDict(from_attributes=True)

class TickerSentimentResponse(BaseModel):
    """Aggregeted sentiment for a specific ticker."""
    status: str = Field(default="success", description="API response status")
    ticker: str = Field(..., description="Requested ticker symbol (e.g., AAPL)")
    time_window: str = Field(..., description="Aggregation period (e.g., '7 days')")
    aggregated_sentiment: str = Field(..., description="Overall trend: bullish, bearish, neutral")
    average_score: float = Field(..., description="Mean sentiment score of recent articles")
    article_count: int = Field(..., description="Number of articles analyzed")
    recent_signals: List[ArticleSignalDTO] = Field(default_factory=list, description="List of recent article signals")