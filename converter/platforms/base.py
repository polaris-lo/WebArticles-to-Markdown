from __future__ import annotations
from abc import ABC, abstractmethod


class BasePlatform(ABC):
    """Abstract base class for all platform extractors.

    Every subclass must implement extract() and return a dict with at least:
      - title (str)
      - body_html (str)   — raw HTML handed to markdownify
      - platform (str)    — canonical platform name

    Optional but recommended:
      - author, date, source_url, tags, categories, summary, extra
    """

    name: str = "unknown"

    @abstractmethod
    def extract(self, url: str, config: dict, cookies: dict) -> dict:
        """Fetch and parse content from the given URL.

        Returns a dict conforming to the extraction schema.
        Raises ExtractionError if the platform cannot extract useful content.
        """


class ExtractionError(Exception):
    """Raised when a platform extractor cannot extract content."""
