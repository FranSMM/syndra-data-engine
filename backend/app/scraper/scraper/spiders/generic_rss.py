import scrapy
from pydantic import ValidationError

from app.schemas.article_schema import ScrapedArticle, ArticlePayload


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
        'USER_AGENT': 'Syndra-DaaS/1.0 (Financial RSS Aggregator)',
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
            raw_url = item.xpath('./link/text()').get()
            raw_title = item.xpath('./title/text()').get()
            raw_description = item.xpath('./description/text()').get()
            raw_pub_date = item.xpath('./pubDate/text()').get()

            if not raw_url or not raw_pub_date:
                continue

            try:
                valid_article = ScrapedArticle(
                    id=ScrapedArticle.generate_id(raw_url),
                    url=raw_url,
                    source=self.feed_source_name,
                    source_type=self.feed_source_type,
                    title=raw_title,
                    published_at=raw_pub_date,
                    payload={
                        'description': raw_description
                    }
                )

                yield valid_article.model_dump(mode='json')

            except ValidationError as e:
                self.logger.error(f"Pydantic validation failed for URL {raw_url}: {e}")
