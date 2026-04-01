import subprocess
from pathlib import Path
from prefect import task, flow, get_run_logger

# (Extraction Task) Fault-tolerant with 2 retries if the website does down
@task(name="Extract Scrapy Spider", retries=2, retry_delay_seconds=10)
def run_extraction():
    logger = get_run_logger()
    logger.info("Starting Scrapy extraction...")

    scraper_dir = Path(__file__).parent / "scraper"

    # Run Scrapy isolating its asynchronous motor (Twisted)
    result = subprocess.run(
        ["scrapy", "crawl", "yahoo_finance", "-O", "test_output.json"],
        cwd=scraper_dir,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        logger.error(f"Critical failure in Scrapy: {result.stderr}")
        raise RuntimeError("Extraction node failed")

    logger.info("Successfull extraction. JSON generated.")

# (Load Task) - Safe to re-run
@task(name="Load: PostgreSQL async")
def run_load():
    logger = get_run_logger()
    logger.info("Starting async load to DB...")

    backend_dir = Path(__file__).parent.parent

    # Run the async loader
    result = subprocess.run(
        ["python", "-m", "app.scraper.load_to_db"],
        cwd=backend_dir,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        logger.error(f"Critical failure in Load: {result.stderr}")
        raise RuntimeError("Load node failed")

    logger.info(f"Successfull load to DB: \n{result.stderr}\n{result.stdout}")

@task(name="MLOps: Sentiment Enrichment", retries=1)
def run_enrichment():
    logger = get_run_logger()
    logger.info("Starting local ML inference (FinBERT)...")

    backend_dir = Path(__file__).parent.parent

    # Run the enrichment script in an isolated process
    # Architecture benefit: 0S reclaims the 400MB RAM when the process dies.
    result = subprocess.run(
        ["python", "-m", "app.ml.enrich_sentiment"],
        cwd=backend_dir,
        capture_output=True,
        text=True
    ) 

    if result.returncode != 0:
        logger.error(f"Critical failure in Enrichment: {result.stderr}")
        raise RuntimeError("Enrichment node failed")

    if result.stdout:
        logger.info(f"Enrichment stdout: \n{result.stdout}")
    if result.stderr:
        logger.error(f"Enrichment stderr (model logs/warnings): \n{result.stderr}")

    logger.info("Successfull enrichment. Scores calculated.")

@task(name="MLOps: Vector Indexing", retries=1)
def run_vectorization():
    logger = get_run_logger()
    logger.info("Starting semantic vector geenration (all-MiniLM-L6-v2 on CPU)...")

    backend_dir = Path(__file__).parent.parent

    result = subprocess.run(
        ["python", "-m", "app.backfill_vectors"],
        cwd=backend_dir,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        logger.error(f"Critical failure in Backfill: {result.stderr}")
        raise RuntimeError("Backfill node failed")

    if result.stdout:
        logger.info(f"Vectorization stdout: \n{result.stdout}")
    if result.stderr:
        logger.error(f"Vectorization stderr (model logs/warnings): \n{result.stderr}")

    logger.info(f"Vectorization completed: \n{result.stdout}. Qdrant is up to date.")


# Master Flow (DAG)
@flow(name="ETL Pipeline: Syndra Financial Ingestion")
def etl_flow():
    logger = get_run_logger()
    logger.info("Waking up the Syndra DaaS Engine...")

    # Strict definition of the sequence: Extract -> Validate (Scrapy) -> Load (SQLAlchemy)
    run_extraction()

    # Bronze Layer: Extraction & Load
    run_load()   

    # Silver Layer: Financial Sentiment Enrichment
    run_enrichment()

    # Gold Layer: Semantic Search Indexing
    run_vectorization()

    logger.info("ETL Pipeline completed successfully. Syndra Data is ready for API consumption.")

# Entry point for Prefect UI
if __name__ == "__main__":
    # To run it manually once (testing), uncomment the following line:
    etl_flow() 

    """
    # To leave it running automatically (Production):
    etl_flow.serve(
        name="syndra-nightly-ingestion", 
        cron="0 3 * * *", # Runs every day at 3:00 AM
        tags=["syndra", "fintech", "etl", "production"], 
        description="Automated nightly ingestion of financial news into PostgreSQL"
    )
    """