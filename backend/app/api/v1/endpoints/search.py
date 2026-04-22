from fastapi import APIRouter, Query, HTTPException
from app.db.vector_store import qdrant, COLLECTION_NAME
from app.services.embedding_service import get_embedding_engine
from typing import List, Dict, Any, Optional
import logging

from app.api.deps import verify_api_key
from app.models.api_key import APIKey
from fastapi import Depends
from qdrant_client.models import Filter, FieldCondition, MatchValue

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/semantic", response_model=List[Dict[str, Any]])
async def semantic_search(
    query: str = Query(..., min_length=3, description="Semantic concept to search for"),
    ticker: Optional[str] = Query(None, description="Filter by specific ticker"),
    limit: int = Query(default=5, ge=1, le=20, description="Maximum number of results"),
    client: APIKey = Depends(verify_api_key)
):
   """
   Perform a semantic similarity search across financial news
   """
   try:
       logger.info(f"Search API | Client: {client.client_name} | Query: {query} | Ticker: {ticker}")
       # Generate embedding for the query
       query_embedding = get_embedding_engine().get_embedding(query)

       # Set up hybrid search filter if ticker is provided
       query_filter = None
       if ticker:
           query_filter = Filter(
               must=[
                   FieldCondition(
                       key="tickers",
                       match=MatchValue(value=ticker.upper())
                   )
               ]
           )

       # Search in Qdrant (using the updated API for qdrant-client 1.17+)
       search_response = qdrant.query_points(
           collection_name=COLLECTION_NAME,
           query=query_embedding.tolist(),
           query_filter=query_filter,
           limit=limit,
           with_payload=True,
       )
       search_result = search_response.points

       # Format results (DaaS Contract)
       results = []
       for hit in search_result:
           results.append({
               "article_id": hit.payload.get("article_id"),
               "tickers": hit.payload.get("tickers"),
               "similarity_score": round(hit.score, 4),
               "title": hit.payload.get("title", "unknown")
           })

       return results

   except Exception as e:
       logger.error(f"Search failed: {str(e)}")
       raise HTTPException(status_code=500, detail="Internal search engine error")