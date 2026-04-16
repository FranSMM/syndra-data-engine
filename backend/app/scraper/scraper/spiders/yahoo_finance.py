# NOT USING CURRENTLY - USING GENERIC RSS SPIDER INSTEAD

import scrapy
from pydantic import ValidationError

# to adjust the import path according to the project settings
from app.schemas.article_schema import ScrapedArticle, ArticlePayload

class YahooFinanceRssSpider(scrapy.Spider):
    name = "yahoo_finance"
    allowed_domains = ["yahoo.com"]

    # RSS feed URL for El País
    start_urls = ["https://finance.yahoo.com/news/rssindex"]

    # Custom settings to adjust the spider's behavior (anti-blocking settings)
    custom_setting = {
        'ROBOTSTXT_OBEY': False,
        'USER_AGENT': 'Syndra-DaaS/1.0 (Financial RSS Aggregator)',
        'DOWNLOAD_DELAY': 1.0
    }


    def parse(self, response):
        # RSS feeds use <item> tags for each article
        articles = response.xpath('//item')

        self.logger.info(f"Found {len(articles)} financial articles in the Yahoo Finance RSS feed.")

        for item in articles:
            raw_url = item.xpath('./link/text()').get()
            raw_title = item.xpath('./title/text()').get()
            raw_description = item.xpath('./description/text()').get()
            raw_pub_date = item.xpath('./pubDate/text()').get()

            if not raw_url or not raw_pub_date:
                continue # Skip malformed RSS items

            try: 
                valid_article = ScrapedArticle(
                    id=ScrapedArticle.generate_id(raw_url),
                    url=raw_url,
                    source=self.name,
                    title=raw_title,
                    published_at=raw_pub_date,
                    payload={
                        'description': raw_description
                    }
                )

                yield valid_article.model_dump(mode='json')

            except ValidationError as e:
                self.logger.error(f"Pydantic validation failed for URL {raw_url}: {e}")
                
    