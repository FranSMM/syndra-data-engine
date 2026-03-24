FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /code

# 1. Primero solo requirements para cachear esta capa
COPY requirements.txt /code/

# 2. Instalar torch con CUDA antes que el resto de dependencias
RUN pip install torch --index-url https://download.pytorch.org/whl/cu121 \
    && pip install --no-cache-dir --upgrade -r requirements.txt

# 3. Luego el código (cambios aquí no invalidan el caché de dependencias)
COPY alembic.ini /code/
COPY ./alembic /code/alembic
COPY ./app /code/app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]