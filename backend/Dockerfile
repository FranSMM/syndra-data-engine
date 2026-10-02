# Base and every package pinned: a rebuild must produce the same image, not the
# newest versions of the day. To upgrade, regenerate constraints.txt on purpose.
FROM python:3.11.16-slim@sha256:e41613d42d4891e4930f79523f93f81bbc7632584ec65e36ab055f41a800b41e

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /code

# Copy requirements to cache this layer
COPY requirements.txt constraints.txt /code/

# Install torch (CPU version for the VPS) and other dependencies
RUN pip install torch==2.14.0+cpu --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt -c constraints.txt

# Both models baked in at pinned revisions; the app reads the same ENV (ADR 042)
ENV HF_HOME=/models_cache \
    FINBERT_MODEL_NAME=ProsusAI/finbert \
    FINBERT_REVISION=4556d13015211d73dccd3fdd39d39232506f3e43 \
    EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2 \
    EMBEDDING_MODEL_REVISION=1110a243fdf4706b3f48f1d95db1a4f5529b4d41
ARG LOAD_MODELS="import os; \
from transformers import pipeline; \
from sentence_transformers import SentenceTransformer; \
pipeline('sentiment-analysis', model=os.environ['FINBERT_MODEL_NAME'], tokenizer=os.environ['FINBERT_MODEL_NAME'], revision=os.environ['FINBERT_REVISION']); \
SentenceTransformer(os.environ['EMBEDDING_MODEL_NAME'], revision=os.environ['EMBEDDING_MODEL_REVISION'], device='cpu')"
# Download, then load again offline: a file missing at run time fails the build instead
RUN python -c "$LOAD_MODELS" && HF_HUB_OFFLINE=1 python -c "$LOAD_MODELS"
# No Hub access at run time
ENV HF_HUB_OFFLINE=1

# Copy code (changes here won't invalidate the dependencies/models cache)
COPY alembic.ini /code/
COPY ./alembic /code/alembic
COPY ./data /code/data
COPY ./app /code/app

# Production-safe default. This is the exact image pushed to GHCR and pulled by
# the VPS, so it must never boot with --reload: the reloader spawns a file
# watcher, burns CPU/RAM and is explicitly unsupported for production serving.
# Local development re-enables hot reload through the `command:` override in
# docker-compose.yml, mirroring how docker-compose.prod.yml sets --workers 1.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]