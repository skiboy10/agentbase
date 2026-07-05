"""
Web scraper orchestrator.

Main WebScraper class that coordinates scanning and scraping operations.
"""

import asyncio
from typing import Optional
from urllib.parse import urlparse
import structlog

from .types import SiteNode, ScrapedPage
from .browser import BrowserManager
from .parser import normalize_url, get_path_prefix, extract_links, extract_title, extract_content
from .tree_builder import build_tree_from_urls, organize_nodes_into_tree
from .sitemap import fetch_sitemap_urls
from app.core.url_validator import validate_url_safe

logger = structlog.get_logger()

# Titles that indicate a JS-heavy page has not yet hydrated its content.
# Treat these as unhydrated and retry once with extra wait time.
_PLACEHOLDER_TITLES = frozenset({
    "Failed to load",
    "Loading...",
    "Loading…",  # ellipsis character
    "Just a moment...",
    "Just a moment…",
    "",
})


def _looks_unhydrated(title: str, child_count: int) -> bool:
    """Return True if the page appears to be a JS loading shell.

    Detects both placeholder titles (Cloudflare, React loading screens) and
    pages that fetched successfully but produced no child links — which is a
    strong signal the content wasn't rendered yet.
    """
    return title.strip() in _PLACEHOLDER_TITLES


class WebScraper:
    """Web scraper using Playwright for robust bot-resistant scraping."""

    def __init__(self):
        self._browser = BrowserManager()

    async def close(self):
        """Close the browser."""
        await self._browser.close()

    async def scan_url(
        self,
        base_url: str,
        max_depth: int = 2,
        path_scope: Optional[str] = None,
    ) -> SiteNode:
        """
        Scan a URL and discover linked pages within the same path prefix.

        Args:
            base_url: The starting URL to scan
            max_depth: Maximum depth of link following (default 2)
            path_scope: Custom path scope to filter links (e.g., "/guide" to get all /guide/* pages)
                       If not provided, auto-detects from base_url

        Returns:
            SiteNode tree structure of discovered pages
        """
        base_url = normalize_url(base_url)

        # Use custom path scope or auto-detect from URL
        if path_scope:
            # Ensure path_scope starts with / and doesn't end with /
            path_scope = path_scope.strip()
            if not path_scope.startswith('/'):
                path_scope = '/' + path_scope
            path_prefix = path_scope.rstrip('/')
        else:
            path_prefix = get_path_prefix(base_url)

        logger.info("Starting URL scan with Playwright", url=base_url, path_prefix=path_prefix, max_depth=max_depth)

        # Track visited URLs and their info
        visited: dict[str, SiteNode] = {}
        seen: set[str] = {base_url}  # all URLs ever queued (prevents duplicate fetches)
        to_visit: list[tuple[str, int]] = [(base_url, 0)]  # (url, depth)

        try:
            while to_visit:
                url, depth = to_visit.pop(0)

                if url in visited:
                    continue

                soup, error = await self._browser.fetch_page(url)

                if error:
                    logger.warning("Failed to fetch page", url=url, error=error)
                    continue

                if soup is None:
                    continue

                title = extract_title(soup)

                # If the page looks unhydrated (placeholder title), retry once
                # with an explicit extra wait to give the JS framework time to
                # render. This is needed for sites like crowleymarine.com that
                # use React/Next.js and aren't fully rendered after networkidle.
                if _looks_unhydrated(title, 0):
                    logger.info(
                        "Page appears unhydrated, retrying with extra wait",
                        url=url,
                        title=title,
                    )
                    # Ensure a fresh browser context picks up the retry
                    await self._browser.close()
                    await asyncio.sleep(5)
                    soup2, error2 = await self._browser.fetch_page(url)
                    if soup2 is not None:
                        retry_title = extract_title(soup2)
                        if not _looks_unhydrated(retry_title, 0):
                            soup = soup2
                            title = retry_title
                            logger.info("Retry hydration succeeded", url=url, title=title)
                        else:
                            # Still unhydrated — record a visible error node
                            # instead of silently returning an empty success.
                            logger.warning(
                                "Page did not hydrate after networkidle + 5 s retry — "
                                "JS-rendered site; consider using sitemap mode or WebFetch",
                                url=url,
                                title=retry_title,
                            )
                            parsed = urlparse(url)
                            root = SiteNode(
                                url=url,
                                title=(
                                    f"[hydration-failed] {retry_title or 'Failed to load'} — "
                                    "JS-rendered site; use sitemap_url or WebFetch"
                                ),
                                path=parsed.path,
                            )
                            return root
                    else:
                        logger.warning("Retry fetch also failed", url=url, error=error2)

                parsed = urlparse(url)

                # Create node for this page
                node = SiteNode(
                    url=url,
                    title=title,
                    path=parsed.path,
                )
                visited[url] = node

                logger.info("Scanned page", url=url, title=title, depth=depth)

                # Only follow links if we haven't reached max depth
                if depth < max_depth:
                    links = extract_links(soup, url, path_prefix)
                    for link in links:
                        if link not in visited and link not in seen:
                            # Validate each discovered link before queueing (SSRF protection)
                            if validate_url_safe(link) is not None:
                                seen.add(link)
                                to_visit.append((link, depth + 1))

            # Build tree structure from flat visited dict
            root = visited.get(base_url)
            if not root:
                # Create empty root if base URL failed
                parsed = urlparse(base_url)
                root = SiteNode(url=base_url, title="Failed to load", path=parsed.path)

            # Organize pages into tree by path
            organize_nodes_into_tree(root, list(visited.values()), base_url)

            logger.info("Scan complete", total_pages=len(visited))

            return root

        finally:
            # Clean up browser resources
            await self.close()

    async def scan_sitemap(
        self,
        sitemap_url: str,
        path_filter: Optional[str] = None,
        max_urls: int = 25000,
    ) -> SiteNode:
        """
        Scan a sitemap to discover URLs.

        This is useful for sites that use JavaScript navigation where
        traditional link crawling doesn't work.

        Args:
            sitemap_url: URL of the sitemap.xml
            path_filter: Optional path substring to filter URLs (e.g., "/guide/")
            max_urls: Maximum number of URLs to return

        Returns:
            SiteNode tree structure of discovered pages
        """
        logger.info(
            "Starting sitemap scan",
            sitemap_url=sitemap_url,
            path_filter=path_filter,
            max_urls=max_urls,
        )

        # Fetch URLs from sitemap
        urls = await fetch_sitemap_urls(sitemap_url, path_filter, max_urls)

        if not urls:
            return SiteNode(
                url=sitemap_url,
                title="No URLs found",
                path="/",
            )

        # Build tree structure from URLs
        tree = build_tree_from_urls(
            urls,
            base_title=f"Sitemap ({len(urls)} pages)"
        )

        logger.info("Sitemap scan complete", total_urls=len(urls))

        return tree

    async def scrape_page(self, url: str) -> ScrapedPage:
        """
        Scrape content from a single page.

        Args:
            url: URL to scrape

        Returns:
            ScrapedPage with extracted content
        """
        soup, error = await self._browser.fetch_page(url)

        if error or soup is None:
            return ScrapedPage(
                url=url,
                title="",
                content="",
                success=False,
                error=error or "Failed to parse page"
            )

        title = extract_title(soup)
        content = extract_content(soup)

        # Include raw HTML for code preservation (if enabled in config)
        from app.core.config import get_settings
        settings = get_settings()
        raw_html = str(soup) if settings.code_preservation_enabled else None

        return ScrapedPage(
            url=url,
            title=title,
            content=content,
            success=True,
            html=raw_html
        )

    async def scrape_pages(self, urls: list[str]) -> list[ScrapedPage]:
        """
        Scrape content from multiple pages.

        Args:
            urls: List of URLs to scrape

        Returns:
            List of ScrapedPage objects
        """
        logger.info("Starting batch scrape with Playwright", total_urls=len(urls))

        try:
            results = []
            for url in urls:
                result = await self.scrape_page(url)
                results.append(result)

            successful = sum(1 for r in results if r.success)
            logger.info("Batch scrape complete", successful=successful, total=len(urls))

            return results
        finally:
            await self.close()
