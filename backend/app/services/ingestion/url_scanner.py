"""
URL scanning functionality.

Handles URL structure scanning including sitemap discovery and crawling.
"""
from typing import Optional

import structlog

from .types import SiteTreeNode, ScanResult

logger = structlog.get_logger()


class UrlScanner:
    """
    Scans URLs to discover site structure.

    Supports three modes:
    - Auto-discover: Automatically finds and parses sitemaps
    - Sitemap: Uses provided sitemap URL
    - Crawl: Crawls links from the given URL
    """

    async def scan_url(
        self,
        url: str,
        max_depth: int = 2,
        path_scope: Optional[str] = None,
        sitemap_url: Optional[str] = None,
        path_filter: Optional[str] = None,
        auto_discover_sitemap: bool = False
    ) -> ScanResult:
        """
        Scan a URL and return the site tree structure.

        Three modes:
        1. Auto-discover mode: If auto_discover_sitemap=True, discovers sitemap automatically
        2. Sitemap mode: If sitemap_url is provided, fetches URLs from sitemap
        3. Crawl mode (fallback): Crawls the given URL, discovers linked pages
        """
        from app.services.web_scraper import get_scraper, discover_sitemap

        def convert_tree(node) -> SiteTreeNode:
            return SiteTreeNode(
                url=node.url,
                title=node.title,
                path=node.path,
                children=[convert_tree(child) for child in node.children],
            )

        scraper = get_scraper()
        discovered_sitemap_url: Optional[str] = None

        # Auto-discover sitemap if requested
        if auto_discover_sitemap and not sitemap_url:
            if not url.startswith(('http://', 'https://')):
                raise ValueError("URL must start with http:// or https://")

            logger.info("Auto-discovering sitemap", url=url)
            discovered_sitemap_url = await discover_sitemap(url)

            if discovered_sitemap_url:
                logger.info(
                    "Starting sitemap scan with discovered sitemap",
                    sitemap_url=discovered_sitemap_url,
                    path_filter=path_filter,
                )
                tree = await scraper.scan_sitemap(
                    sitemap_url=discovered_sitemap_url,
                    path_filter=path_filter,
                    max_urls=25000,
                )
                return ScanResult(
                    tree=convert_tree(tree),
                    sitemap_url=discovered_sitemap_url,
                )
            else:
                logger.info("No sitemap discovered, falling back to crawl mode", url=url)

        # Explicit sitemap mode
        if sitemap_url:
            if not sitemap_url.startswith(('http://', 'https://')):
                raise ValueError("Sitemap URL must start with http:// or https://")

            logger.info(
                "Starting sitemap scan",
                sitemap_url=sitemap_url,
                path_filter=path_filter,
            )
            tree = await scraper.scan_sitemap(
                sitemap_url=sitemap_url,
                path_filter=path_filter,
                max_urls=25000,
            )
            return ScanResult(
                tree=convert_tree(tree),
                sitemap_url=sitemap_url,
            )

        # Crawl mode (default or fallback)
        if not url.startswith(('http://', 'https://')):
            raise ValueError("URL must start with http:// or https://")

        logger.info(
            "Starting URL scan",
            url=url,
            max_depth=max_depth,
            path_scope=path_scope,
        )
        tree = await scraper.scan_url(
            url,
            max_depth=max_depth,
            path_scope=path_scope,
        )

        return ScanResult(
            tree=convert_tree(tree),
            sitemap_url=None,
        )
