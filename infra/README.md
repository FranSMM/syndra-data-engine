Infrastructure & DevOps 🐳

This directory contains all IaC (Infrastructure as Code), container configurations, and observability setups for NeuralNews.

🗺 Topology

The docker-compose.yml defines the following services:

api: FastAPI backend.

postgres: Relational database (Port 5432). Stores raw articles, users, and metadata.

qdrant: Vector database (Port 6333). Stores article embeddings and user vectors.

prefect-server: Data pipeline orchestrator.

redis: Caching layer and rate-limiting backend.

prometheus & grafana: Observability stack (Phase 6).

🗄 Volumes & Persistence

Local directory volumes in `./data` are used to ensure data persistence across restarts:

- `./data/postgres`: Postgres storage.
- `./data/qdrant`: Vector embeddings.
- `./data/grafana`: Dashboard configurations (Future).

Warning: Never delete these directories in production unless performing a hard reset.

🔒 Environment Variables

Refer to .env.example in the root directory. Critical variables include:

DATABASE_URL

QDRANT_HOST

JWT_SECRET_KEY

📊 Monitoring

Grafana: http://localhost:3000 (Default credentials in .env)

Key Metrics: API Latency (p95), VRAM usage, ETL pipeline success rate.