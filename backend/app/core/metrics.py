"""
Prometheus domain collectors.

The HTTP metrics (latency, throughput, error rate) come for free from
prometheus-fastapi-instrumentator. What lives here is the half no library can
guess: the facts that make Syndra Syndra — how fresh each source is, how big
the corpus has grown, whether enrichment is keeping up.

Two design points worth keeping in mind before editing this file.

**These gauges are derived, not counted.** Every number below is the answer to a
SQL query, not a counter incremented as the pipeline runs. In-process counters
reset when the container restarts and drift from the database the moment
anything writes to Postgres from outside the API — the scheduler does exactly
that, every hour. Deriving is what the Prometheus exporter guidelines call for
when the backing store already holds the truth, and INC-021 is the local
precedent for what a second copy of the truth costs.

**Never label by ticker.** Sources are three; tickers are 10657. A label per
ticker would be 10657 series per metric in the TSDB head block, which on this
box means an OOM, not a slow dashboard.

A note on the names, because the obvious ones are wrong: none of these gauges
carries a `_total` suffix. Prometheus reserves that suffix for counters —
monotonic, only ever increasing — and `promtool check metrics` rejects it on
anything else ("non-counter metrics should not have _total suffix"). These are
gauges: the corpus shrinks if rows are deleted, and pending falls back to zero
every time the pipeline catches up. Worth getting right the first time, since a
rename starts a fresh series and orphans everything collected before it.
"""
import asyncio
import logging
import time

from prometheus_client import Gauge
from sqlalchemy import and_, func, select

from app.db.session import AsyncSessionLocal
from app.models.article import Article
from app.models.raw_article import RawArticle

logger = logging.getLogger(__name__)

# Prometheus scrapes every 15s; these queries are aggregates over the whole
# corpus. Recomputing them four times a minute buys no resolution that matters
# for numbers that move on an hourly pipeline, so the result is held for 60s and
# scrapes in between are served from the last read.
DOMAIN_METRICS_TTL_SECONDS = 60

# Ingestion states that must always be reported. A state missing from the
# GROUP BY means zero rows in it, and zero is a fact worth graphing — especially
# `failed`, where a flat zero line is the claim being made.
_TRACKED_INGESTION_STATES = ("pending", "failed")


SOURCE_LAST_ARTICLE_AGE = Gauge(
    "syndra_source_last_article_age_seconds",
    "Age of the most recent article published by each source, in seconds",
    ["source"],
)

ARTICLES = Gauge(
    "syndra_articles",
    "Enriched articles in the Silver layer, by source",
    ["source"],
)

INGESTION_PENDING = Gauge(
    "syndra_ingestion_pending",
    "Bronze articles still awaiting enrichment",
)

INGESTION_FAILED = Gauge(
    "syndra_ingestion_failed",
    "Bronze articles whose enrichment failed",
)

ARTICLES_WITH_TICKERS = Gauge(
    "syndra_articles_with_tickers",
    "Enriched articles with at least one extracted ticker",
)

# Not in the original catalogue, added because the gauges above are the kind
# that lie by omission. If Postgres is unreachable the last read stays published
# rather than vanishing, so a frozen corpus size looks identical to a stable
# one. This timestamp is what tells the two apart.
DOMAIN_METRICS_LAST_SUCCESS = Gauge(
    "syndra_domain_metrics_last_success_timestamp_seconds",
    "Unix timestamp of the last successful refresh of the domain gauges",
)


_last_refresh_monotonic: float | None = None
_refresh_lock = asyncio.Lock()


def _source_stats_statement():
    """
    One pass over the Silver layer for the three per-source facts.

    The age is computed in SQL rather than in Python because published_at is a
    naive column: subtracting it from a Python datetime means guessing which
    timezone it is in. `timezone('utc', now())` gives Postgres a naive UTC
    instant to subtract, so the arithmetic happens where the data lives and
    carries no assumption about the container clock.
    """
    return (
        select(
            Article.source.label("source"),
            func.count().label("total"),
            func.count()
            .filter(
                and_(
                    Article.tickers.isnot(None),
                    func.cardinality(Article.tickers) > 0,
                )
            )
            .label("with_tickers"),
            func.extract(
                "epoch",
                func.timezone("utc", func.now()) - func.max(Article.published_at),
            ).label("last_article_age_seconds"),
        )
        .group_by(Article.source)
    )


def _ingestion_states_statement():
    return select(
        RawArticle.ingestion_state.label("state"),
        func.count().label("total"),
    ).group_by(RawArticle.ingestion_state)


def _publish_source_stats(rows) -> None:
    # Gauge children outlive the data behind them: a source removed from
    # feeds.json would keep reporting its final value until the process
    # restarted. Clearing first means a source that stops existing stops being
    # reported, which is the honest representation.
    ARTICLES.clear()
    SOURCE_LAST_ARTICLE_AGE.clear()

    articles_with_tickers = 0
    for row in rows:
        ARTICLES.labels(source=row.source).set(row.total)
        articles_with_tickers += row.with_tickers or 0

        # NULL when every row of that source lacks a published date. Reporting
        # 0 would read as "published a moment ago"; no series at all is what
        # "unknown" actually looks like in Prometheus.
        if row.last_article_age_seconds is not None:
            SOURCE_LAST_ARTICLE_AGE.labels(source=row.source).set(
                row.last_article_age_seconds
            )

    ARTICLES_WITH_TICKERS.set(articles_with_tickers)


def _publish_ingestion_states(rows) -> None:
    counts = {state: 0 for state in _TRACKED_INGESTION_STATES}
    for row in rows:
        if row.state in counts:
            counts[row.state] = row.total

    INGESTION_PENDING.set(counts["pending"])
    INGESTION_FAILED.set(counts["failed"])


async def refresh_domain_metrics(session_factory=None, *, force: bool = False) -> bool:
    """
    Re-read the domain gauges from Postgres, at most once every TTL.

    Returns True when the database was actually queried, False when the call was
    served from the cache or the read failed. Never raises: /metrics has to keep
    serving the HTTP histograms even with Postgres down, because those are the
    numbers a latency chapter is built from.
    """
    global _last_refresh_monotonic

    session_factory = session_factory or AsyncSessionLocal
    now = time.monotonic()

    if not force and _last_refresh_monotonic is not None:
        if now - _last_refresh_monotonic < DOMAIN_METRICS_TTL_SECONDS:
            return False

    async with _refresh_lock:
        # Re-checked inside the lock: concurrent scrapes queue here, and without
        # this the second one would run the same queries the first just ran.
        now = time.monotonic()
        if not force and _last_refresh_monotonic is not None:
            if now - _last_refresh_monotonic < DOMAIN_METRICS_TTL_SECONDS:
                return False

        try:
            async with session_factory() as session:
                source_rows = (await session.execute(_source_stats_statement())).all()
                state_rows = (await session.execute(_ingestion_states_statement())).all()
        except Exception as exc:
            # Deliberately broad: a scrape is not a request path, and there is
            # no caller to hand the failure to. The previous values stay
            # published and DOMAIN_METRICS_LAST_SUCCESS stops advancing, which
            # is how a consumer notices they are stale.
            logger.warning("Domain metrics refresh failed: %s", exc)
            return False

        _publish_source_stats(source_rows)
        _publish_ingestion_states(state_rows)

        _last_refresh_monotonic = time.monotonic()
        DOMAIN_METRICS_LAST_SUCCESS.set(time.time())
        return True
