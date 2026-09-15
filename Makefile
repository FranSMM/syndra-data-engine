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

# ==============================================================================
# Production VPS Port-Forwarding (SSH Tunneling)
# ==============================================================================
# El usuario y la IP salen del .env, que esta en .gitignore. Un Makefile se
# commitea; un .env no. Mismo sitio del que los lee deploy.sh, asi que no hay
# dos copias que puedan divergir.
#
# Se leen solo esas dos lineas en vez de hacer `include .env`: ese fichero lleva
# contraseñas y URLs con '=' dentro, y make intentaria interpretarlo entero.
VPS_USER := $(shell grep -E '^VPS_USER=' .env 2>/dev/null | tail -1 | cut -d= -f2-)
VPS_IP   := $(shell grep -E '^VPS_IP=' .env 2>/dev/null | tail -1 | cut -d= -f2-)

# Sin esto, un .env ausente produce `ssh @` y un error incomprensible.
_require-vps:
	@test -n "$(VPS_IP)" -a -n "$(VPS_USER)" || { \
		echo "Faltan VPS_USER o VPS_IP en el .env de la raiz del repo."; exit 1; }

pf: web
web: _require-vps
	@echo "==> Abriendo paneles de monitorizacion web (VPS)..."
	@echo " -> Prefect:    http://localhost:4200"
	@echo " -> Prometheus: http://localhost:9090 (activo en Fase 6)"
	@echo " -> Qdrant:     http://localhost:6333/dashboard"
	@echo "Presiona Ctrl+C para cerrar el tunel."
	ssh -N -L 4200:localhost:4200 -L 9090:localhost:9090 -L 6333:localhost:6333 $(VPS_USER)@$(VPS_IP)

vps-status: _require-vps
	@ssh $(VPS_USER)@$(VPS_IP) "docker stats --no-stream --format 'table {{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}' && echo '' && free -h"
# ==============================================================================
# Observabilidad
# ==============================================================================
# Chequeo completo del stack de metricas. Solo lectura, no toca produccion.
#
# El script sale con codigo != 0 cuando hay avisos, que es lo que quieres en un
# cron. Aqui se traga a proposito: esto lo lanza una persona que ya esta leyendo
# los avisos en pantalla, y un "make: *** Error 1" al final solo parece que la
# herramienta se ha roto. Para automatizar, llama a ./check-observability.sh
# directamente y mira su codigo de salida.
obs:
	@bash ./check-observability.sh || true

# Misma comprobacion sobre una ventana mas larga: make obs-range W=14d
obs-range:
	@bash ./check-observability.sh $(or $(W),14d) || true
