import scrapy
from pydantic import ValidationError

# to adjust the import path according to the project settings
from app.schemas.article_schema import ScrapedArticle

class ElPaisRssSpider(scrapy.Spider):
    name = "elpais_rss"
    allowed_domains = ["elpais.com"]

    # RSS feed URL for El País
    start_urls = ["https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada"]

    def parse(self, response):
        # RSS feeds use <item> tags for each article
        articles = response.xpath('//item')

        self.logger.info(f"Found {len(articles)} articles in the RSS feed.")

        for item in articles:
            raw_url = item.xpath('./link/text()').get()
            raw_title = item.xpath('./title/text()').get()
            raw_description = item.xpath('./description/text()').get()

            try: 
                valid_article = ScrapedArticle(
                    url=raw_url,
                    source=self.name,
                    title=raw_title,
                    payload={
                        'description': raw_description
                    }
                )

                yield valid_article.model_dump(mode='json')

            except ValidationError as e:
                self.logger.error(f"Pydantic validation failed for URL {raw_url}: {e}")
                
    