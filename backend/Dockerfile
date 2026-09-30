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

# Define HuggingFace and pre-download FinBERT model
ENV HF_HOME=/models_cache
RUN python -c "from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
    AutoModelForSequenceClassification.from_pretrained('ProsusAI/finbert'); \
    AutoTokenizer.from_pretrained('ProsusAI/finbert')"

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