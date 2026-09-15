"""
Publication-date normalisation for the Bronze -> Silver boundary.

Bronze stores whatever the feed said, verbatim and forever. Silver stores what
we believe, and this module is where the difference is decided. Kept free of
any heavy import on purpose: the enrichment job that calls it pulls in torch and
FinBERT, and the rules below deserve a test suite that runs anywhere.

Two things happen here, and they fail in different ways.

**Timezone conversion.** Everything downstream — the time-window filter, the
ordering of recent signals, the deduplication heuristic — treats
Article.published_at as naive UTC. An offset-bearing timestamp must therefore be
converted, not stripped. Stripping was the original bug: the SEC emits -05:00,
and "07:00:00-05:00" was being stored as 07:00 instead of 12:00. Five hours is
wider than the 3h deduplication window those timestamps are compared against, so
the same story from two sources stopped collapsing into one signal.

**Plausibility.** A feed can be wrong about its own dates. The SEC's newsroom
feed carries 1990s press releases stamped with the current year; two of them
claimed to be published months after we had already read them. Nothing can be
published after it is ingested, and that single comparison catches the class
without knowing anything about any particular source.
"""
from datetime import datetime, timedelta, timezone

# A publisher's clock can sit slightly ahead of this box, and some feeds stamp
# an item the moment it is scheduled rather than when it appears. The guard is
# for timestamps that cannot be true, not for ones that are merely surprising,
# so it leaves room for both before rejecting anything.
PUBLICATION_CLOCK_SKEW = timedelta(hours=1)


def normalise_published_at(
    raw: str | None,
    ingested_at: datetime | None = None,
) -> datetime | None:
    """
    Turn a stored Bronze timestamp into the naive UTC value Silver holds.

    Returns None when the input is missing, unparseable, or cannot be true.
    None is a deliberate outcome rather than a failure: the article and its
    sentiment are still worth keeping, and a NULL publication date excludes it
    from time-window queries and from the source freshness gauge instead of
    quietly poisoning both. A wrong timestamp is worse than a missing one,
    because everything downstream trusts it.

    `ingested_at` is the Bronze row's created_at. Without it the plausibility
    check is skipped and only the conversion happens.
    """
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)
    # A naive value is assumed to be UTC, the same assumption the ingestion-side
    # normaliser states and for the same reason: the alternative is discarding
    # an otherwise good item.
    parsed = parsed.replace(tzinfo=None)

    if ingested_at is not None and parsed > ingested_at + PUBLICATION_CLOCK_SKEW:
        return None

    return parsed
