# Backend

Code shared by the API and the ETL pipeline. Both run from the same Docker image, built from `Dockerfile` on Python 3.11 with CPU-only PyTorch. FinBERT and all-MiniLM-L6-v2 are downloaded at build time at pinned revisions and loaded offline at runtime (ADR-042).

To run the whole stack, see [Running Locally](../README.md#running-locally) in the root README.

## Layout

```text
backend/
├── app/
│   ├── main.py              # FastAPI application
│   ├── pipeline.py          # Prefect flow: extract, load, sentiment, vector indexing
│   ├── backfill_vectors.py  # Vector indexing stage (Silver to Qdrant)
│   ├── api/                 # Endpoints (sentiment, semantic search) and dependencies
│   ├── core/                # Settings, API key security, Redis, metrics, date and source rules
│   ├── db/                  # Async SQLAlchemy session and Qdrant client
│   ├── models/              # ORM models (Bronze, Silver, API keys)
│   ├── schemas/             # Pydantic response contracts
│   ├── scraper/             # Scrapy RSS spider and the Bronze loader
│   ├── ml/                  # Sentiment enrichment stage
│   ├── services/            # FinBERT, embeddings and ticker extraction
│   └── scripts/             # Maintenance scripts
├── alembic/                 # Database migrations
├── data/                    # feeds.json (RSS sources) and company_tickers.json
└── tests/
```

## Pipeline

`pipeline.py` defines one Prefect flow that the scheduler runs every hour. Each stage runs in its own subprocess, so the memory taken by the models goes back to the system when the stage ends:

1. **Extract:** Scrapy reads the feeds in `data/feeds.json`, one request at a time per domain with a one second delay, identifying itself with its own user agent.
2. **Load:** inserts the new items into Bronze as JSONB, unchanged.
3. **Sentiment:** takes the pending Bronze items, normalises them, extracts their tickers, scores them with FinBERT and writes them to Silver.
4. **Vector indexing:** embeds the new Silver articles with all-MiniLM-L6-v2 and upserts them into Qdrant.

## Migrations

```bash
make makemigrations m="describe the change"
make migrate
```

## Maintenance scripts

Run them inside the API container, for example `docker compose exec api python -m app.scripts.provision_client "name"`. The scripts that rewrite data only write to Silver or Qdrant; Bronze is never modified.

| Script | Purpose |
|---|---|
| `provision_client` | Creates an API key. `--trial N` makes it expire after N days. |
| `backfill_tickers` | Re-extracts tickers for existing articles after `company_tickers.json` changes. |
| `backfill_published_at` | Re-derives publication dates from the original feed string in Bronze. |
| `recalculate_sentiment` | Recomputes the sentiment score of existing articles. |
| `resync_vector_payloads` | Brings Qdrant payloads back in line with Silver. |
| `update_sec_tickers` | Refreshes `company_tickers.json` from the SEC list. |

## Tests

```bash
make test               # unit tests, from the repository root
make test-integration   # security tests against a throwaway stack
```
