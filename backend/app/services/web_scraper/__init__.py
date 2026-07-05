"""
Web scraper package.

Provides WebScraper for robust web scraping with Playwright.
"""

from typing import Optional

# Re-export types
from .types import SiteNode, ScrapedPage

# Re-export sitemap utilities
from .sitemap import fetch_sitemap_urls, discover_sitemap

# Re-export tree builder
from .tree_builder import build_tree_from_urls

# Import main scraper class
from .scraper import WebScraper

# Global scraper instance
_scraper: Optional[WebScraper] = None


def get_scraper() -> WebScraper:
    """Get the global scraper instance."""
    global _scraper
    if _scraper is None:
        _scraper = WebScraper()
    return _scraper


__all__ = [
    # Main class
    "WebScraper",
    # Types
    "SiteNode",
    "ScrapedPage",
    # Sitemap utilities
    "fetch_sitemap_urls",
    "discover_sitemap",
    # Tree builder
    "build_tree_from_urls",
    # Singleton factory
    "get_scraper",
]
