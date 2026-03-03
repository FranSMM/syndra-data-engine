Backend API (NeuralNews) ⚙️

This module contains the core API responsible for serving news, handling search queries (Lexical + Semantic), and managing user data.

🛠 Tech Stack

Framework: FastAPI (Python 3.11+)

Validation: Pydantic v2

Database ORM/Query Builder: SQLAlchemy (Async) / asyncpg

Vector Search Client: Qdrant Client

Caching: Redis

🧩 Key Components

/api/v1/search: Implements Hybrid Search. Combines BM25 scores from PostgreSQL with Cosine Similarity scores from Qdrant using Reciprocal Rank Fusion (RRF).

/api/v1/feed: Serves personalized feeds based on user embedding vectors (RecSys).

/models: Pydantic schemas enforcing strict data validation between the API, Database, and Frontend.

💻 Local Development

If running outside the main docker-compose for isolated testing:

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the Uvicorn server (requires DBs to be up)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000


🧪 Testing

Run pytest to execute unit and integration tests. Ensure DB mocks are active.

pytest tests/
