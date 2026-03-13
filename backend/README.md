# ⚙️ Backend API (`Syndra`)

> **The high-performance REST API module for the Syndra DaaS platform, serving enriched financial intelligence and semantic news data.**

---

## 🛠 Tech Stack 

- **Framework:** `FastAPI` (Python 3.11+)
- **Validation & Data Contracts:** `Pydantic v2`
- **Database ORM & Query Builder:** `SQLAlchemy (Async)` / `asyncpg`
- **Vector Search Client:** `Qdrant Client`
- **Caching:** `Redis`

---

## 🧩 Architectural Principles

### 1. Strict Data Contracts & DTOs (`/models` & `/schemas`)
All incoming and outgoing payloads are strictly validated using **Pydantic v2**. The architecture enforces a rigid separation of Data Transfer Objects (DTOs) defined in `/schemas` from internal database entities and domain models defined in `/models`. This guarantees predictable, type-safe API responses essential for B2B consumption.

### 2. Async-First FastAPI Architecture
Fully asynchronous endpoints built on `FastAPI` and `asyncpg` to handle high-throughput, concurrent downstream requests without blocking the event loop.

### 3. Fail-Fast Validation
Incoming data streams (via the ETL pipeline) and API requests are validated immediately at the boundary layer. Malformed payloads or invalid ticker symbols are rejected eagerly, ensuring system integrity and preventing cascading failures deeper in the pipeline.

### 4. Idempotency
API endpoints and underlying ingestion procedures are explicitly designed for idempotency. Repeating the same extraction or ingestion pipeline will not duplicate database records, ensuring reliable syncs for enterprise downstream consumers.

### 5. ETL Extraction Pipeline (`/scraper` & `pipeline.py`)
Orchestrated by **Prefect**, this pipeline extracts raw financial data using **Scrapy**, validates the schemas, and asynchronously loads them into PostgreSQL, safely handling duplicate content.

---

## 💻 Local Development

If running outside the main `docker-compose` stack for isolated testing or development:

### 1. Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Uvicorn server 
*(Note: Requires the `postgres` and `qdrant` databases to be accessible either locally or via port-forwarding from Docker).*
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 🧪 Testing

Run pytest to execute unit and validation tests against the data contracts. Ensure your DB mocks are correctly configured.
```bash
pytest tests/
```
