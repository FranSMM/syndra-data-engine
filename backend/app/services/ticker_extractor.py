"""
FlashText-based ticker extractor (Aho-Corasick algorithm).
Singleton pattern: dictionary loaded once into RAM, shared across all requests.

Performance: O(N) where N = text length, regardless of dictionary size.
"""
import json
import logging
import os

from flashtext import KeywordProcessor

logger = logging.getLogger(__name__)


class TickerExtractor:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        # Case-sensitive to avoid matching common words like "apple" or "meta"
        self.kp = KeywordProcessor(case_sensitive=True)

        dict_path = os.path.join(
            os.path.dirname(__file__), "../../data/company_tickers.json"
        )
        with open(dict_path, "r", encoding="utf-8") as f:
            ticker_dict = json.load(f)

        # FlashText expects: {'StandardName': ['alias1', 'alias2']}
        # We ensure the ticker itself is always treated as an alias.
        for ticker, aliases in ticker_dict.items():
            if ticker not in aliases:
                aliases.append(ticker)

        self.kp.add_keywords_from_dict(ticker_dict)
        logger.info(
            f"TickerExtractor loaded: {len(ticker_dict)} tickers with "
            f"{sum(len(v) for v in ticker_dict.values())} aliases."
        )

    def extract(self, text: str) -> list[str]:
        """Extract unique ticker symbols found in the text."""
        if not text:
            return []
        return list(set(self.kp.extract_keywords(text)))
