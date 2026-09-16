"""
Per-source publication-date rules.

Kept out of app/core/dates.py on purpose. That module holds rules true of any
feed: an offset must be converted, nothing can be published after it is read,
and stays worth trusting precisely because it knows nothing about any particular
publisher. This module is where a rule that only applies to one source lives, so
the coupling is visible in the import rather than buried in an `if` inside the
enrichment loop.

The rule here exists because the generic guard provably cannot catch one real
case. The SEC's newsroom feed republishes 1990s press releases stamped with the
current year. Two arrived dated months in the future and were rejected; release
99-110, "President's Year 2000 Council", arrived dated 2026-09-07: before we
read it, therefore plausible, and sat in the corpus counted as a recent signal.

What gives it away is that the SEC numbers every press release YEAR-NUMBER and
puts that number in the URL, so the release carries its own true year.

Adding a source: write a checker, register it below. If this ever reaches three
or four entries it is worth asking whether the feeds should be declaring their
own date semantics in feeds.json instead.
"""
import re
from datetime import datetime

# Matches the release number at the start of an SEC newsroom slug: "2026-88-..."
# or "97-114-...". Anchored to the path segment so a number appearing later in
# the headline slug cannot be mistaken for it.
_SEC_RELEASE_NUMBER = re.compile(r"/press-releases/(\d{2}|\d{4})-\d+-")

# The SEC moved from two-digit to four-digit release numbering in the early
# 2000s, so a two-digit prefix is always last century or the very start of this
# one. 50 is a wide margin: the oldest releases in the feed are from 1993.
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
