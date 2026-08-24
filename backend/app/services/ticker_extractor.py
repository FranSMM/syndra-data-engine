"""
FlashText-based ticker extractor (Aho-Corasick algorithm).
Singleton pattern: dictionary loaded once into RAM, shared across all requests.

Performance: O(N) where N = text length, regardless of dictionary size.
"""
import json
import logging
import os
import re

from flashtext import KeywordProcessor

logger = logging.getLogger(__name__)


class TickerExtractor:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    # A bare symbol this short is not evidence of a company being mentioned.
    # "A" is Agilent, "S" is SentinelOne, "P" is Everpure, "AI" is C3.ai — and
    # in ordinary financial prose those characters come from "A colleague",
    # "U.S.", "S&P" and "AI chips". Measured over the corpus, 1-2 character
    # symbols produced 29.4% of all ticker attachments, and 7,451 articles
    # carried nothing else. The company-name aliases are unambiguous and stay
    # registered, so Agilent is still found when it is actually named.
    MIN_BARE_SYMBOL_LEN = 3

    # Aliases that name something other than the company. Each was found in the
    # data, not guessed.
    #   bullish/bearish — BLSH ships "Bullish" and matched every "analysts turn
    #     bullish" headline.
    #   dow, nasdaq     — the index, not Dow Inc. or Nasdaq Inc. Both are named
    #     far more often as market barometers than as listed companies:
    #     "Dow hits record, S&P 500, Nasdaq slip".
    STOP_ALIASES = {"bullish", "bearish", "dow", "nasdaq"}

    # Warrants and preferred classes should not absorb a mention of the company.
    # "Morgan Stanley Maintains Overweight Rating on ..." was tagging MS-PL, a
    # preferred series, rather than MS. Same for ACHR-WT, JOBY-WT and the -P*
    # series. Ordinary share classes (BRK.B) are genuine securities and stay.
    DERIVATIVE_SUFFIX = re.compile(r"-(WT|P[A-Z]|R|U)$")

    @staticmethod
    def _normalise(alias) -> str:
        """Lowercased, with the trailing punctuation the source data carries."""
        return str(alias).strip().rstrip(", \t").lower()

    def _initialize(self):
        # Case-sensitive to avoid matching common words like "apple" or "meta"
        self.kp = KeywordProcessor(case_sensitive=True)

        dict_path = os.path.join(
            os.path.dirname(__file__), "../../data/company_tickers.json"
        )
        with open(dict_path, "r", encoding="utf-8") as f:
            ticker_dict = json.load(f)

        # FlashText expects: {'StandardName': ['alias1', 'alias2']}
        cleaned: dict[str, list[str]] = {}
        dropped_symbols = dropped_aliases = added_trimmed = dropped_derivatives = 0
        for ticker, aliases in ticker_dict.items():
            # Warrants and preferred series never carry the company's news.
            if self.DERIVATIVE_SUFFIX.search(ticker):
                dropped_derivatives += 1
                continue

            # Compare against the TRIMMED form. The stored alias is "Nasdaq,"
            # with a trailing comma, so a naive lower() check never matched the
            # stop word and the trimming below then registered a clean "Nasdaq"
            # that fired on every index reference.
            keep = [a for a in aliases
                    if self._normalise(a) not in self.STOP_ALIASES]
            dropped_aliases += len(aliases) - len(keep)

            # The upstream SEC file derives aliases by truncating "X, Inc.",
            # which leaves a trailing comma: "Agilent Technologies,". FlashText
            # matches keywords exactly, so that alias never fires on the far
            # more common "Agilent Technologies beat expectations". 2,997
            # tickers had *every* alias ending in punctuation, and 69 of those
            # are 1-2 character symbols — which, with the bare symbol withheld
            # above, would make Altria, Zoom, DuPont and Agilent unfindable
            # altogether. Registering the trimmed form as well fixes that and
            # adds ~8,300 usable aliases across the dictionary.
            for alias in list(keep):
                trimmed = str(alias).rstrip(", \t")
                if trimmed and trimmed != alias and trimmed not in keep:
                    keep.append(trimmed)
                    added_trimmed += 1

            # The ticker itself is a keyword only when it is long enough to be
            # unambiguous on its own.
            if len(ticker) >= self.MIN_BARE_SYMBOL_LEN:
                if ticker not in keep:
                    keep.append(ticker)
            else:
                dropped_symbols += 1

            if keep:
                cleaned[ticker] = keep

        self.kp.add_keywords_from_dict(cleaned)
        logger.info(
            f"TickerExtractor loaded: {len(cleaned)} tickers with "
            f"{sum(len(v) for v in cleaned.values())} aliases "
            f"({dropped_symbols} bare short symbols and {dropped_aliases} "
            f"common-word aliases withheld, {added_trimmed} trimmed forms added, "
            f"{dropped_derivatives} warrant/preferred tickers excluded)."
        )

    def extract(self, text: str) -> list[str]:
        """Extract unique ticker symbols found in the text."""
        if not text:
            return []
        return list(set(self.kp.extract_keywords(text)))
