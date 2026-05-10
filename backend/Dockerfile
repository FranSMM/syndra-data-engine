FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /code

# Copy requirements to cache this layer
COPY requirements.txt /code/

# Install torch (CPU version for the VPS) and other dependencies
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --upgrade -r requirements.txt

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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]