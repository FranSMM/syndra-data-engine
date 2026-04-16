include .env
export

# ==============================================================================
# Infrastructure (Docker)
# ==============================================================================
up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose up -d --build

bash:
	docker compose exec backend bash

# Connecting to the DB using the correct credentials from .env
db-shell:
	docker compose exec postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

# ==============================================================================
# Database Migrations (Alembic)
# ==============================================================================
# Usage: make makemigrations m="migration message"
makemigrations:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

migrate:
	docker compose exec api alembic upgrade head

# ==============================================================================
# Manual ETL Pipeline (Scrapy + Pydantic + SQLAlchemy)
# ==============================================================================
crawl:
	docker compose exec api bash -c "cd app/scraper && export PYTHONPATH=/code && scrapy crawl generic_rss -O test_output.json"

load:
	docker compose exec api python -m app.scraper.load_to_db

# Full testing pipeline
etl-test: crawl load

# Prefect Pipeline
run-etl:
	docker compose exec api python app/pipeline.py