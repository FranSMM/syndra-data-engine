FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /code

# 1. Primero solo requirements para cachear esta capa
COPY requirements.txt /code/

# 2. Instalar torch (versión CPU para el VPS) y resto de dependencias
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir --upgrade -r requirements.txt

# 3. Definir la caché de HuggingFace y pre-descargar el modelo FinBERT (Tarea 1)
ENV HF_HOME=/models_cache
RUN python -c "from transformers import AutoModelForSequenceClassification, AutoTokenizer; \
    AutoModelForSequenceClassification.from_pretrained('ProsusAI/finbert'); \
    AutoTokenizer.from_pretrained('ProsusAI/finbert')"

# 4. Luego el código (cambios aquí no invalidan el caché de dependencias y modelos)
COPY alembic.ini /code/
COPY ./alembic /code/alembic
COPY ./data /code/data
COPY ./app /code/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]