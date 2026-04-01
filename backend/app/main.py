from fastapi import FastAPI
from app.core.config import settings
from app.api.v1.endpoints import sentiment, search

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Institutional-grade sentiment analysis API for financial markets.",
    version="1.0.0",
)

app.include_router(sentiment.router, prefix="/api/v1/sentiment", tags=["Sentiment Analysis"])
app.include_router(search.router, prefix="/api/v1/search", tags=["Semantic Search"])

@app.get("/")
def root():
    return {"message": "Welcome to Syndra API", "docs": "/docs"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "syndra-api"}