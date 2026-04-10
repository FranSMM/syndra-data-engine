import subprocess
import json
from pathlib import Path
from prefect import task, flow, get_run_logger
from datetime import timedelta
import sys

SCRAPER_DIR = Path(__file__).parent / "scraper"
FEEDS_CONFIG_PATH = Path(__file__).parent.parent / "data" / "feeds.json"
OUTPUT_PATTERN = "*_output.json"

def _load_feeds() -> list[dict]:
    """Load and filter enabled feeds from the BYOS feeds.json config."""
    if not FEEDS_CONFIG_PATH.exists():
        raise FileNotFoundError(f"feeds.json not found at {FEEDS_CONFIG_PATH}")
    with open(FEEDS_CONFIG_PATH, 'r') as f:
        feeds = json.load(f)
    return [feed for feed in feeds if feed.get("enabled", True)]


# (Extraction Task) Fault-tolerant with 2 retries if the website goes down
@task(name="Extract: Generic RSS Spiders", retries=2, retry_delay_seconds=10)
def run_extraction():
    logger = get_run_logger()

    feeds = _load_feeds()
    logger.info(f"BYOS: {len(feeds)} active feed(s) loaded from feeds.json.")

    # Clean stale output files from previous runs to avoid loading old data
    for old_file in SCRAPER_DIR.glob(OUTPUT_PATTERN):
        old_file.unlink()
        logger.debug(f"Cleaned old output: {old_file.name}")

    for feed in feeds:
        feed_name = feed["name"]
        feed_url = feed["url"]
        source_type = feed.get("source_type", "rss_feed")
        output_file = f"{feed_name}_output.json"

        logger.info(f"Crawling source '{feed_name}' ({source_type}): {feed_url}")

        # Each feed writes to its own file — no data loss between sources
        result = subprocess.run(
            [
                "scrapy", "crawl", "generic_rss",
                "-a", f"target_url={feed_url}",
                "-a", f"source_name={feed_name}",
                "-a", f"source_type={source_type}",
                "-O", output_file
            ],
            cwd=SCRAPER_DIR,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logger.error(f"Scrapy failed for source '{feed_name}': {result.stderr}")
            raise RuntimeError(f"Extraction failed for source: {feed_name}")

    logger.info("All BYOS sources extracted successfully.")

# (Load Task) - Safe to re-run (idempotent via content_hash)
@task(name="Load: PostgreSQL async")
def run_load():
    logger = get_run_logger()

    output_files = list(SCRAPER_DIR.glob(OUTPUT_PATTERN))
    if not output_files:
        logger.warning("No output files found. Skipping load.")
        return

    logger.info(f"Loading {len(output_files)} output file(s) into PostgreSQL...")
    backend_dir = Path(__file__).parent.parent

    for output_file in output_files:
        logger.info(f"Loading: {output_file.name}")

        result = subprocess.run(
            ["python", "-m", "app.scraper.load_to_db", str(output_file)],
            cwd=backend_dir,
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            logger.error(f"Load failed for {output_file.name}: {result.stderr}")
            raise RuntimeError(f"Load failed for: {output_file.name}")

    logger.info(f"All sources loaded to DB successfully.\n{result.stdout}")

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
    # Manual execution for recovery
    # e.g.: docker exec -it syndra_scheduler python -m app.pipeline --manual
    if "--manual" in sys.argv:
        print("Running pipeline manually (One-Off Run)...")
        etl_flow()
    else:
        # Normal scheduler mode
        print("Starting Prefect scheduler (Execution every 60m)...")
        etl_flow.serve(
            name="syndra-hourly-deployment",
            interval=timedelta(minutes=60),
            description="Syndra's end-to-end pipeline: Extraction, NLP, and Vectorization."
        )