"""
Publication-date normalisation for the Bronze -> Silver boundary.

Article.published_at is naive UTC, so an offset-bearing timestamp must be
converted rather than stripped. Feeds can also be wrong about their own dates,
and nothing can be published after it was ingested.

No heavy imports, so these rules stay testable outside the ETL image.
See ADR 037.
"""
from datetime import datetime, timedelta, timezone

# Publisher clocks drift and some feeds stamp an item when it is scheduled. The
# guard is for dates that cannot be true, not for ones that are surprising.
PUBLICATION_CLOCK_SKEW = timedelta(hours=1)


def normalise_published_at(
    raw: str | None,
    ingested_at: datetime | None = None,
) -> datetime | None:
    """
    Turn a stored Bronze timestamp into the naive UTC value Silver holds.

    Returns None when the input is missing, unparseable, or cannot be true. A
    wrong timestamp is worse than a missing one, because everything downstream
    trusts it; NULL merely excludes the article from time-window queries.

    `ingested_at` is the Bronze row's created_at. Without it only the timezone
    conversion happens.
    """
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    # A naive value is assumed UTC, same as the ingestion-side normaliser.
    parsed = parsed.replace(tzinfo=None)

    if ingested_at is not None and parsed > ingested_at + PUBLICATION_CLOCK_SKEW:
        return None

    return parsed
