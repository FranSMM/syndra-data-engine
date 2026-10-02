include .env
export

# Local development (Docker)

up: check-mounts
	docker compose up -d

down:
	docker compose down

build: check-mounts
	docker compose up -d --build

bash:
	docker compose exec backend bash

db-shell:
	docker compose exec postgres psql -U ${POSTGRES_USER} -d ${POSTGRES_DB}

# Migrations (Alembic)

# make makemigrations m="message"
makemigrations:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

migrate:
	docker compose exec api alembic upgrade head

# Manual ETL

crawl:
	docker compose exec api bash -c "cd app/scraper && export PYTHONPATH=/code && scrapy crawl generic_rss -O test_output.json"

load:
	docker compose exec api python -m app.scraper.load_to_db

etl-test: crawl load

run-etl:
	docker compose exec api python app/pipeline.py

# Production VPS

# Without this check an incomplete .env runs `ssh @` and fails with an unclear error.
_require-vps:
	@test -n "$(VPS_IP)" -a -n "$(VPS_USER)" || { \
		echo "VPS_USER or VPS_IP missing from the root .env."; exit 1; }

# SSH tunnel to the web panels
pf: web
web: _require-vps
	@echo " -> Prefect:    http://localhost:4200"
	@echo " -> Prometheus: http://localhost:9090"
	@echo " -> Qdrant:     http://localhost:6333/dashboard"
	@echo "Ctrl+C closes the tunnel."
	ssh -N -L 4200:localhost:4200 -L 9090:localhost:9090 -L 6333:localhost:6333 $(VPS_USER)@$(VPS_IP)

vps-status: _require-vps
	@ssh $(VPS_USER)@$(VPS_IP) "docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' && echo '' && free -h"

# Observability (read-only)

# The script exits non-zero on warnings, for cron. Ignored here because a person
# is reading them; automation should call ./check-observability.sh directly.
obs:
	@bash ./check-observability.sh || true

# make obs-range W=14d
obs-range:
	@bash ./check-observability.sh $(or $(W),14d) || true

# Tests

# A missing bind mount source makes Docker create an empty directory and the
# container fails with a misleading exit 127.
check-mounts:
	@bash ./check-compose-mounts.sh

# Runs on a throwaway stack, never production: it inserts API keys (one is
# hardcoded in the test) and sends 100 requests to trigger a 429.
test-integration:
	@bash ./run-integration-tests.sh

test:
	@docker compose run --rm --no-deps api python -m pytest /code/tests \
		--ignore=/code/tests/test_security.py -q
