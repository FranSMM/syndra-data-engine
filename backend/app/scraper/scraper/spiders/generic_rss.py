from datetime import timezone
from email.utils import parsedate_to_datetime

import scrapy
from pydantic import ValidationError

from app.schemas.article_schema import ScrapedArticle, ArticlePayload


def normalise_pub_date(raw: str) -> str:
    """
    Convert an RSS <pubDate> into something Pydantic accepts.

    RSS 2.0 mandates RFC 822 dates ("Wed, 12 Aug 2026 19:36:21 -0400"), and
    Pydantic v2 does not parse that format: it accepts ISO 8601. Every item
    from a standards-compliant feed therefore failed validation and was
    silently dropped, which is why this pipeline ran on a single source for
    months: Yahoo Finance happens to emit ISO 8601 instead, so it was the only
    feed that ever worked. Measured before the fix: MarketWatch 0/10, BBC 0/52,
    FT 0/25, SEC 0/25 accepted.

    Returns an ISO 8601 string when the input is RFC 822, and the input
    untouched otherwise so ISO-emitting feeds keep working unchanged.

    A date with no timezone is assumed to be UTC. That is a real assumption,
    not a certainty: RFC 822 permits omitting the offset, but the alternative
    is discarding the item, and the downstream layers already treat stored
    timestamps as naive UTC.
    """
    if not raw:
        return raw
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return raw          # not RFC 822: let Pydantic try ISO 8601
    if parsed is None:      # older Pythons signal failure this way
        return raw
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.isoformat()


class GenericRssSpider(scrapy.Spider):
    """
    Source-agnostic RSS spider for the BYOS (Bring Your Own Source) architecture.
    Receives target_url and source_name dynamically via CLI arguments:
        scrapy crawl generic_rss -a target_url=https://... -a source_name=my_feed
    """
    name = "generic_rss"

    # Custom settings to adjust the spider's behavior
    custom_settings = {
        'ROBOTSTXT_OBEY': False,
        # A contact address is not decoration: the SEC requires automated
        # clients to identify themselves with one, and throttles or blocks
        # those that do not. Other publishers treat an anonymous agent the
        # same way.
        'USER_AGENT': 'Syndra-DaaS/1.0 (Financial RSS Aggregator; syndradata@gmail.com)',
        'DOWNLOAD_DELAY': 1.0
    }

    def __init__(self, target_url=None, source_name=None, source_type="rss_feed", *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not target_url:
            raise ValueError("target_url is required. Usage: scrapy crawl generic_rss -a target_url=<URL>")

        self.start_urls = [target_url]
        self.feed_source_name = source_name or self._derive_source_name(target_url)
        self.feed_source_type = source_type

    @staticmethod
    def _derive_source_name(url: str) -> str:
        """Fallback: extract a clean source name from the URL domain."""
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        # 'finance.yahoo.com' -> 'finance_yahoo_com'
        return domain.replace(".", "_").replace("-", "_")

    def parse(self, response):
        articles = response.xpath('//item')

        self.logger.info(f"Found {len(articles)} articles from source '{self.feed_source_name}'.")

        for item in articles:
            # Strip on extraction. Feeds indent their XML, and the SEC's in
            # particular wraps titles in whitespace: untrimmed, that leading
            # padding reaches the Silver Layer, skews the SequenceMatcher ratio
            # the late deduplication depends on (ADR 033), and shows up verbatim
            # in API responses.
            raw_url = (item.xpath('./link/text()').get() or '').strip()
            raw_title = (item.xpath('./title/text()').get() or '').strip()
            raw_description = (item.xpath('./description/text()').get() or '').strip()
            raw_pub_date = (item.xpath('./pubDate/text()').get() or '').strip()

            if not raw_url or not raw_pub_date:
                continue

            try:
                valid_article = ScrapedArticle(
                    id=ScrapedArticle.generate_id(raw_url),
                    url=raw_url,
                    source=self.feed_source_name,
                    source_type=self.feed_source_type,
                    title=raw_title,
                    published_at=normalise_pub_date(raw_pub_date),
                    payload={
                        'description': raw_description
                    }
                )

                yield valid_article.model_dump(mode='json')

            except ValidationError as e:
                self.logger.error(f"Pydantic validation failed for URL {raw_url}: {e}")
