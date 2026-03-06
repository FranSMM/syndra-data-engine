# Will contain Pydantic schema for Article data transfer
# This are the schemeas:

from pydantic import BaseModel, HttpUrl, Field
from typing import Any, Dict

class ScrapedArticle(BaseModel):

    # HttpUrl ensures the URL is valid (starts with http:// or https://)
    url: HttpUrl

    # Newspaper's identifies (e.g., 'el_pais')
    source: str = Field(..., description="Newspaper's identifier", min_length=2, max_length=100)

    # Article's title (is technically part of the payload, but we keep it here)
    title: str = Field(..., min_length=5)

    # Catch-all dictionary for everything else (author, full text, html tags, date)
    # This directly maps to JSONB column in Postgres
    payload: Dict[str, Any] = Field(default_factory=dict)