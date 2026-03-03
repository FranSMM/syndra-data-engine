NeuralNews🧠📰

Intelligent News Aggregator leveraging Edge AI, Hybrid Search, and robust Data Engineering.

NeuralNews is designed to combat "infoxication" through semantic understanding of news articles and user-aligned personalized feeds. Built with a strict Docker-First, Microservices-oriented Monorepo architecture.

🏗 System Architecture

The project follows a modular pipeline:

Data Engineering (ETL): Scrapy + Prefect extracting and validating data into a raw Postgres layer.

MLOps (Batch Inference): Local LLMs (llama.cpp + GGUF) summarizing and generating embeddings (sentence-transformers).

High-Performance Backend: Async FastAPI serving Hybrid Search (BM25 + Vector) via Qdrant & Postgres.

RecSys: User-vector profiling based on reading history.

📂 Monorepo Structure

neuralnews/
├── backend/          # FastAPI application, Pydantic models, ML inference routers
├── frontend/         # MVP UI (Streamlit / React)
├── infra/            # Nginx, Prometheus/Grafana configs (Future)
├── docs/             # Extended architecture documents (C4 models)
├── docker-compose.yml# Main Docker infrastructure configuration
├── .env.example      # Global environment variables template
└── README.md         # This file


🚀 Quickstart (Docker-First)

The entire stack is containerized. No local dependencies required other than Docker and Docker Compose.

# 1. Clone the repository
git clone [https://github.com/FranSMM/neural-news.git](https://github.com/FranSMM/neural-news.git)
cd neural-news

# 2. Setup environment variables
cp .env.example .env

# 3. Spin up the infrastructure (Detached mode)
docker-compose up -d

