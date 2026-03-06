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
	docker compose exec db psql -U neural_user -d neural_db

# ==============================================================================
# Database Migrations (Alembic)
# ==============================================================================
# Usage: make makemigrations m="migration message"
makemigrations:
	docker compose exec backend alembic revision --autogenerate -m "$(m)"

migrate:
	docker compose exec backend alembic upgrade head

# ==============================================================================
# Manual ETL Pipeline (Scrapy + Pydantic + SQLAlchemy)
# ==============================================================================
crawl:
	docker compose exec backend bash -c "cd app/scraper && export PYTHONPATH=/code && scrapy crawl elpais_rss -O test_output.json"

load:
	docker compose exec backend python -m app.scraper.load_to_db

# Full testing pipeline
etl-test: crawl load

# Prefect Pipeline
run-etl:
	docker compose exec backend python -m app.pipeline