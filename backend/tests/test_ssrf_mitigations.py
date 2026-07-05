"""
Tests for #50 SSRF mitigations in the web scraper.

Covers:
- BrowserManager.fetch_page rejects unsafe URLs before any browser activity.
- BrowserManager._ssrf_route_guard aborts unsafe routes (initial + redirects).
- BrowserManager._httpx_fallback does not follow redirects to private IPs.
"""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.services.web_scraper.browser import BrowserManager


@pytest.mark.asyncio
async def test_fetch_page_rejects_unsafe_url_at_entry():
    """Initial URL pointing to a private IP must not reach the browser."""
    bm = BrowserManager()
    soup, err = await bm.fetch_page("http://127.0.0.1:5432/")
    assert soup is None
    assert err is not None
    assert "SSRF" in err


@pytest.mark.asyncio
async def test_fetch_page_rejects_decimal_encoded_loopback():
    """http://2130706433/ is loopback in decimal — must be blocked too."""
    bm = BrowserManager()
    soup, err = await bm.fetch_page("http://2130706433/")
    assert soup is None
    assert err is not None
    assert "SSRF" in err


@pytest.mark.asyncio
async def test_ssrf_route_guard_aborts_unsafe_request():
    """Route guard aborts when the request URL is blocked."""
    bm = BrowserManager()

    request = MagicMock()
    request.url = "http://127.0.0.1:5432/foo"
    request.resource_type = "document"

    route = MagicMock()
    route.request = request
    route.abort = AsyncMock()
    route.continue_ = AsyncMock()

    await bm._ssrf_route_guard(route)
    route.abort.assert_awaited_once()
    route.continue_.assert_not_called()


@pytest.mark.asyncio
async def test_ssrf_route_guard_continues_safe_request():
    """Route guard continues when the request URL passes validation."""
    bm = BrowserManager()

    request = MagicMock()
    request.url = "https://example.com/foo"
    request.resource_type = "document"

    route = MagicMock()
    route.request = request
    route.abort = AsyncMock()
    route.continue_ = AsyncMock()

    await bm._ssrf_route_guard(route)
    route.continue_.assert_awaited_once()
    route.abort.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("non_http_url", [
    "about:blank",
    "data:text/html,<p>hi</p>",
    "blob:https://example.com/abc",
    "chrome-extension://abc/xyz",
])
async def test_ssrf_route_guard_passes_non_http_schemes(non_http_url):
    """Playwright bootstraps pages with about:blank etc. — these must not be aborted."""
    bm = BrowserManager()

    request = MagicMock()
    request.url = non_http_url
    request.resource_type = "document"

    route = MagicMock()
    route.request = request
    route.abort = AsyncMock()
    route.continue_ = AsyncMock()

    await bm._ssrf_route_guard(route)
    route.continue_.assert_awaited_once()
    route.abort.assert_not_called()


@pytest.mark.asyncio
async def test_httpx_fallback_blocks_redirect_to_private_ip():
    """A safe URL that 302s to a private IP must be blocked at the next hop.

    This is the core #50 fix: previously httpx.follow_redirects=True would
    silently follow attacker.com → 127.0.0.1:5432 and reach internal services.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://127.0.0.1:5432/admin"})
        # If our fix is broken, the test would reach this branch and we'd
        # see a 200 leaking the redirect target.
        return httpx.Response(200, text="<html>secret</html>", headers={"content-type": "text/html"})

    bm = BrowserManager()
    transport = httpx.MockTransport(handler)

    # Patch httpx.AsyncClient to use our mock transport so we don't need
    # to monkey-patch the fallback method itself.
    original_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    import app.services.web_scraper.browser as browser_mod
    browser_mod.httpx.AsyncClient = patched_async_client
    try:
        soup, err = await bm._httpx_fallback("http://example.com/")
    finally:
        browser_mod.httpx.AsyncClient = original_async_client

    assert soup is None
    assert err is not None
    assert "Blocked by SSRF policy" in err


@pytest.mark.asyncio
async def test_httpx_fallback_follows_safe_redirects():
    """Public-to-public redirect chains still work.

    Uses example.com (IANA-reserved, resolves to a real public IP) for both
    hops with different paths so DNS validation passes while httpx.MockTransport
    intercepts the actual HTTP I/O.
    """
    hop_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal hop_count
        hop_count += 1
        if request.url.path == "/":
            return httpx.Response(302, headers={"location": "http://example.com/page"})
        if request.url.path == "/page":
            return httpx.Response(
                200, text="<html>ok</html>", headers={"content-type": "text/html"}
            )
        return httpx.Response(404)

    bm = BrowserManager()
    transport = httpx.MockTransport(handler)

    original_async_client = httpx.AsyncClient

    def patched_async_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_async_client(*args, **kwargs)

    import app.services.web_scraper.browser as browser_mod
    browser_mod.httpx.AsyncClient = patched_async_client
    try:
        soup, err = await bm._httpx_fallback("http://example.com/")
    finally:
        browser_mod.httpx.AsyncClient = original_async_client

    assert err is None
    assert soup is not None
    assert hop_count == 2  # redirect + final
