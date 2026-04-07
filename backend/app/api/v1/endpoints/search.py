from fastapi import APIRouter, Query, HTTPException
from app.db.vector_store import qdrant, COLLECTION_NAME
from app.services.embedding_service import embedding_engine
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/semantic", response_model=List[Dict[str, Any]])
async def semantic_search(
    query: str = Query(..., min_length=3, description="Semantic concept to search for"),
    limit: int = Query(default=5, ge=1, le=20, description="Maximum number of results")
):
   """
   Perform a semantic similarity search across financial news
   """
   try:
       # Generate embedding for the query
       query_embedding = embedding_engine.get_embedding(query)

       # Search in Qdrant (using the updated API for qdrant-client 1.17+)
       search_response = qdrant.query_points(
           collection_name=COLLECTION_NAME,
           query=query_embedding.tolist(),
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
       raise HTTPException(status_code=500, detail=str(e))