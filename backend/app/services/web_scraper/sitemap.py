"""
Sitemap discovery and parsing.

Handles fetching and parsing XML sitemaps for URL discovery.
"""

import xml.etree.ElementTree as ET
from typing import Optional
from urllib.parse import urlparse
import httpx
import structlog

from .types import COMMON_SITEMAP_PATHS
from app.core.url_validator import validate_url, validate_url_safe

logger = structlog.get_logger()


async def fetch_sitemap_urls(
    sitemap_url: str,
    path_filter: Optional[str] = None,
    max_urls: int = 25000,
) -> list[str]:
    """
    Fetch and parse a sitemap XML to extract URLs.

    Handles both sitemap index files and regular sitemaps.

    Args:
        sitemap_url: URL of the sitemap.xml
        path_filter: Optional path substring to filter URLs (e.g., "/guide/")
        max_urls: Maximum number of URLs to return

    Returns:
        List of URLs from the sitemap matching the filter
    """
    # Validate the sitemap URL itself before fetching (SSRF protection)
    validate_url(sitemap_url)

    urls = []

    # follow_redirects=False — redirects to internal addresses are a SSRF vector.
    # Each redirect destination must be independently validated before following.
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        try:
            response = await client.get(sitemap_url)
            response.raise_for_status()
            content = response.text

            # Parse XML
            root = ET.fromstring(content)

            # Handle namespace (sitemaps use xmlns)
            ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

            # Check if this is a sitemap index
            sitemap_refs = root.findall('.//sm:sitemap/sm:loc', ns)
            if sitemap_refs:
                # This is a sitemap index, fetch each referenced sitemap
                logger.info("Found sitemap index", sitemap_count=len(sitemap_refs))
                for sitemap_ref in sitemap_refs:
                    if len(urls) >= max_urls:
                        break
                    sub_sitemap_url = sitemap_ref.text
                    if sub_sitemap_url:
                        # Validate each sub-sitemap URL before fetching (SSRF protection)
                        if validate_url_safe(sub_sitemap_url) is None:
                            continue
                        sub_urls = await _fetch_single_sitemap(
                            client, sub_sitemap_url, path_filter, max_urls - len(urls)
                        )
                        urls.extend(sub_urls)
            else:
                # This is a regular sitemap
                urls = await _fetch_single_sitemap(client, sitemap_url, path_filter, max_urls, content)

        except Exception as e:
            logger.error("Failed to fetch sitemap", url=sitemap_url, error=str(e))
            raise

    logger.info("Sitemap URLs fetched", total=len(urls), filter=path_filter)
    return urls[:max_urls]


async def _fetch_single_sitemap(
    client: httpx.AsyncClient,
    sitemap_url: str,
    path_filter: Optional[str],
    max_urls: int,
    content: Optional[str] = None,
) -> list[str]:
    """Fetch and parse a single sitemap file."""
    urls = []

    try:
        if content is None:
            response = await client.get(sitemap_url)
            response.raise_for_status()
            content = response.text

        root = ET.fromstring(content)
        ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

        # Find all URL entries
        url_elements = root.findall('.//sm:url/sm:loc', ns)

        for url_elem in url_elements:
            if len(urls) >= max_urls:
                break

            url = url_elem.text
            if url:
                # Apply path filter if specified
                if path_filter:
                    if path_filter in url:
                        urls.append(url)
                else:
                    urls.append(url)

    except Exception as e:
        logger.warning("Failed to parse sitemap", url=sitemap_url, error=str(e))

    return urls


async def discover_sitemap(base_url: str) -> Optional[str]:
    """
    Auto-discover sitemap URL for a given website.

    Checks:
    1. robots.txt for Sitemap: directives
    2. Common sitemap locations

    Args:
        base_url: Base URL of the website (e.g., "https://example.com" or "https://example.com/docs/page.html")

    Returns:
        Sitemap URL if found, None otherwise
    """
    # Validate base_url before constructing any derived URLs (SSRF protection)
    validate_url(base_url)

    # Extract base domain from URL
    parsed = urlparse(base_url)
    base_domain = f"{parsed.scheme}://{parsed.netloc}"

    logger.info("Discovering sitemap", base_url=base_url, base_domain=base_domain)

    # follow_redirects=False — redirects to internal addresses are a SSRF vector.
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
        # Step 1: Check robots.txt for Sitemap directives
        robots_url = f"{base_domain}/robots.txt"
        try:
            response = await client.get(robots_url)
            if response.status_code == 200:
                # Parse robots.txt for Sitemap: lines
                for line in response.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith('sitemap:'):
                        sitemap_url = line.split(':', 1)[1].strip()
                        # Validate before fetching — robots.txt content is attacker-controlled
                        if validate_url_safe(sitemap_url) is None:
                            continue
                        # Verify it's actually a sitemap
                        if await _verify_sitemap(client, sitemap_url):
                            logger.info("Found sitemap in robots.txt", sitemap_url=sitemap_url)
                            return sitemap_url
        except Exception as e:
            logger.debug("Failed to fetch robots.txt", url=robots_url, error=str(e))

        # Step 2: Try common sitemap locations
        for path in COMMON_SITEMAP_PATHS:
            sitemap_url = f"{base_domain}{path}"
            if await _verify_sitemap(client, sitemap_url):
                logger.info("Found sitemap at common location", sitemap_url=sitemap_url)
                return sitemap_url

    logger.warning("No sitemap found", base_url=base_url)
    return None


async def _verify_sitemap(client: httpx.AsyncClient, url: str) -> bool:
    """Verify that a URL is a valid sitemap by checking response."""
    try:
        response = await client.head(url)
        if response.status_code != 200:
            return False

        # Check content type suggests XML
        content_type = response.headers.get('content-type', '')
        if 'xml' in content_type or 'text/plain' in content_type:
            return True

        # If content-type is ambiguous, try GET and check for XML content
        response = await client.get(url)
        if response.status_code == 200:
            content = response.text[:500]  # Check first 500 chars
            if '<?xml' in content or '<urlset' in content or '<sitemapindex' in content:
                return True

        return False
    except Exception:
        return False
