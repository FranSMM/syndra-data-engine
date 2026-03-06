# 🐳 Infrastructure & DevOps 

> **This directory contains all IaC (Infrastructure as Code), container configurations, and observability setups for Syndra.**

---

## 🗺 Topology

The root `docker-compose.yml` defines the following critical services:

- **🕸️ api:** The FastAPI backend.
- **🐘 postgres:** The Relational Database (`Port 5432`). Stores raw articles, users, and metadata.
- **📐 qdrant:** The Vector Database (`Port 6333`). Stores article embeddings and user vectors.
- **⚡ redis:** Caching layer and rate-limiting backend.
- ** orchestrator:** `prefect-server` data pipeline orchestrator.
- **📈 metrics (Phase 6):** `prometheus` & `grafana` observability stack.

---

## 🗄 Volumes & Persistence

Local directory volumes inside `./data` are used to ensure data persistence across container restarts:

```text
data/
├── postgres/          # Relational data storage
├── qdrant/            # Vector embeddings storage
└── grafana/           # Dashboard configurations (Future)
```

> ⚠️ **Warning:** Never delete these directories in production unless performing a deliberate hard reset.

---

## 🔒 Environment Variables

Refer to `.env.example` in the root directory. Critical variables include:

- `DATABASE_URL`
- `QDRANT_HOST`
- `JWT_SECRET_KEY`

---

## 📊 Monitoring

- **Grafana Dashboard:** `http://localhost:3000` *(Default credentials mapped in `.env`)*
- **Key Metrics to Track:**
  - API Latency (p95)
  - VRAM usage
  - ETL pipeline success rate