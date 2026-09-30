"""
Per-source publication-date rules.

Separate from app/core/dates.py, which only holds rules true of any feed and
stays trustworthy because it knows nothing about any publisher. Source-specific
coupling lives here, visible in an import rather than in an `if` inside the
enrichment loop.

The SEC republishes 1990s press releases stamped with the current year. Some
are dated in the past, so the generic guard cannot see them; the release number
in the URL carries the real year. See ADR 037.

Adding a source: write a checker, register it in _RULES. Past three or four,
reconsider and let feeds.json declare its own date semantics instead.
"""
import re
from datetime import datetime

# Release number at the start of an SEC newsroom slug: "2026-88-", "97-114-".
# Anchored to the path segment so digits in the headline cannot match.
_SEC_RELEASE_NUMBER = re.compile(r"/press-releases/(\d{2}|\d{4})-\d+-")

# Two-digit numbering ran until the early 2000s. The oldest releases in the
# feed are from 1993, so 50 is a wide margin.
_TWO_DIGIT_PIVOT = 50


def _sec_release_year(url: str) -> int | None:
    match = _SEC_RELEASE_NUMBER.search(url or "")
    if not match:
        return None

    raw = match.group(1)
    if len(raw) == 4:
        return int(raw)

    value = int(raw)
    return 1900 + value if value >= _TWO_DIGIT_PIVOT else 2000 + value


def _sec_year_disagrees(url: str, published_at: datetime) -> bool:
    release_year = _sec_release_year(url)
    if release_year is None:
        # No number means no opinion. This rule may only reject on evidence:
        # absence of evidence must never start discarding real articles.
        return False
    return release_year != published_at.year


_RULES = {
    "sec_press_releases": _sec_year_disagrees,
}


def has_implausible_publication_year(
    source: str,
    url: str | None,
    published_at: datetime | None,
) -> bool:
    """
    True when a source-specific rule contradicts the date the feed supplied.

    Returns False for every source without a rule, which is all of them but one,
    and False whenever there is nothing to contradict.
    """
    if published_at is None:
        return False

    rule = _RULES.get(source)
    if rule is None:
        return False

    return rule(url or "", published_at)
