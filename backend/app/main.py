from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(title=settings.PROJECT_NAME)

@app.get("/")
def root():
    return {"message": "Welcome to Syndra API", "docs": "/docs"}

@app.get("/health")
def health_check():
    return {"status": "ok", "db": "not_connected_yet"}