# ⚙️ Backend API (`Syndra`)

> **This module contains the core API responsible for serving news, handling search queries (Lexical + Semantic), and managing user data.**

---

## 🛠 Tech Stack 

- **Framework:** `FastAPI` (Python 3.11+)
- **Validation:** `Pydantic v2`
- **Database ORM & Query Builder:** `SQLAlchemy (Async)` / `asyncpg`
- **Vector Search Client:** `Qdrant Client`
- **Caching:** `Redis`

---

## 🧩 Key Components

### 1. **Hybrid Search (`/api/v1/search`)**
Implements advanced Hybrid Search mechanisms. Combines *BM25* scores from PostgreSQL with *Cosine Similarity* scores from Qdrant using **Reciprocal Rank Fusion (RRF)** for unparalleled search accuracy.

### 2. **Personalized Feed (`/api/v1/feed`)**
Serves curated, personalized feeds based on user embedding vectors (`RecSys`).

### 3. **Data Validation (`/models` & `/schemas`)**
Pydantic schemas enforcing strict data validation between the API boundaries, the Database, and the Frontend consumers.

### 4. **ETL Extraction Pipeline (`/scraper` & `pipeline.py`)**
Orchestrated by **Prefect**, this pipeline extracts raw articles from RSS feeds using **Scrapy**, validates the schemas, and asynchronously loads them into PostgreSQL safely handling duplicate content.

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

Run pytest to execute unit and integration tests. Ensure your DB mocks are correctly configured.
```bash
pytest tests/
```
