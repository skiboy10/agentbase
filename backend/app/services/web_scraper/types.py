"""
Web scraper data types and constants.
"""

from dataclasses import dataclass, field
from typing import Optional

# Common sitemap locations to check
COMMON_SITEMAP_PATHS = [
    '/sitemap.xml',
    '/sitemap-1.xml',
    '/sitemap_index.xml',
    '/sitemap-index.xml',
    '/sitemaps/sitemap.xml',
    '/sitemap/sitemap.xml',
]

# Rate limiting settings
REQUEST_DELAY = 0.5  # 500ms between requests for stealth
REQUEST_TIMEOUT = 30000  # 30 second timeout per page (ms for playwright)
MAX_CONCURRENT = 2  # In-flight Playwright pages per crawl. Each Chromium page can
                    # hold 100-300 MiB resident; with backend capped at 3 GiB and
                    # large JS-heavy sites (SPA-rendered documentation portals), 5 concurrent
                    # pages reliably exhausted memory and triggered "Target crashed"
                    # cascades. 2 keeps peak memory predictable.


@dataclass
class SiteNode:
    """Represents a node in the site tree structure."""
    url: str
    title: str
    path: str
    children: list['SiteNode'] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "url": self.url,
            "title": self.title,
            "path": self.path,
            "children": [child.to_dict() for child in self.children],
        }

    def flatten_urls(self) -> list[str]:
        """Get all URLs in this tree as a flat list."""
        urls = [self.url]
        for child in self.children:
            urls.extend(child.flatten_urls())
        return urls


@dataclass
class ScrapedPage:
    """Represents scraped content from a single page."""
    url: str
    title: str
    content: str
    success: bool = True
    error: Optional[str] = None
    html: Optional[str] = None  # Raw HTML for code preservation
