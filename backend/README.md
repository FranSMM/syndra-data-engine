# ⚙️ Backend API (`Syndra`) - Internal Developer Guide

> **SECURITY CLASSIFICATION:** INTERNAL / CONFIDENTIAL
> The high-performance REST API module for the Syndra DaaS platform. This document contains proprietary infrastructure execution flows, NLP tuning references, and scraping evasion architectures. **Do NOT expose this to public repositories.**

---

## 🛠 Tech Stack 

- **Framework:** `FastAPI` (Python 3.11+)
- **Validation & Data Contracts:** `Pydantic v2`
- **Database ORM & Query Builder:** `SQLAlchemy (Async)` / `asyncpg`
- **Vector Search Client:** `Qdrant Client`
- **Machine Learning Layer:** `PyTorch`, `sentence-transformers` (FinBERT)
- **Data Engineering:** `Prefect 3.0`, `Scrapy`

---

## 🚀 Native / Docker-First Environment Setup

For deterministic builds and avoiding dependency hell (e.g., CUDA drift or PEP 668 limits on Linux), development heavily favors our Docker container workflows.

### 1. Environment & Network
Configure your local environment by copying the example globals. The template lives in `backend/`, but the working `.env` belongs at the **repository root** — that is where Compose and `deploy.sh` read it from. Ensure no sensitive B2B keys or production DB passwords are committed:
```bash
# from the repository root
cp backend/.env.example .env
```
*`POSTGRES_SERVER` must be set to `postgres` (the Compose service name), not `db` or `localhost` — Alembic resolves it as a DNS name from inside the container.*

### 2. General Infrastructure Spin-up
Deploy the backing databases (Postgres & Qdrant) alongside the FastAPI orchestration API.
```bash
docker compose up -d
```
*Note: If you run into `PermissionError 13` or database lock errors on WSL2, refer to the incident logs: `docs/troubleshooting/001_docker_wsl_permissionerror_13.md`.*

### 3. Executing the Complete ETL Pipeline
The data ingestion and enrichment pipeline operates totally decoupled from the API endpoints. We execute the extraction (Scrapy), validation, load, and internal ML inference via our monolithic operations Makefile.
```bash
make run-etl
```
*This command fires the Prefect orchestration to scrape, score via FinBERT, and index embeddings inside Qdrant automatically.*

### 4. Local API Endpoints
Bypass commercial gateways for isolated structural testing:
```bash
curl -X GET "http://localhost:8000/api/v1/sentiment/AAPL" \
     -H "Accept: application/json"
```

---

## 🔒 Proprietary IP / Core NLP Algorithms

All evasion heuristics, FinBERT model tuning, and mathematical normalization logic reside in this codebase. They must be vigorously protected:

- **Mathematical Normalized Sentiment:** Our B2B edge relies on non-rounded sentiment values evaluated over absolute continuous thresholds via HuggingFace's probabilistic pipelines. Do not default back to strict labels (`bullish`/`bearish`) without returning the continuous `sentiment_score`.
- **Scrapy Anti-Bot Evasion:** We rotate User-Agents to emulate normalized Chromium clients on Windows to bypass `robots.txt` or heuristic blocks, notably on `Yahoo Finance`. Refer to the spider configuration inside `app/scraper/` and avoid leaking proxy-rotation logics.
- **Medallion Triggers:** The transition of `RawArticle` from `pending` -> `loaded` -> `processed` triggers our internal Qdrant backfilling logic. Do not bypass the SQLAlchemy models (ORM) to insert into DB directly, as it disrupts the Prefect queues.

---

## 💻 Bare-Metal Execution (Without Docker)

If you must run the stack outside the main `docker-compose` stack (e.g., for detailed GPU profiling or unit testing without container orchestration overhead):

```bash
# 1. Virtual Environment Setup
python3 -m venv venv
source venv/bin/activate

# 2. Dependency Resolution
pip install -r requirements.txt

# 3. Uvicorn Execution 
# (Ensure Postgres and Qdrant are mapped to 127.0.0.1 on the host)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Testing Enforcements
Run `pytest` to execute unit and validation tests against Pydantic data contracts. Never branch off without ensuring data contracts remain intact.
```bash
pytest tests/
```
