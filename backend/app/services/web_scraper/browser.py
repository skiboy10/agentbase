"""
Playwright browser management.

Handles browser lifecycle and page fetching with stealth settings,
crash recovery, periodic recycle, and a hard outer fetch timeout to
prevent the indexer from hanging on wedged Chromium processes (see #127).
"""

import asyncio
from typing import Optional
from bs4 import BeautifulSoup
import httpx
import structlog

from app.core.url_validator import validate_url, validate_url_safe

from .types import REQUEST_DELAY, REQUEST_TIMEOUT, MAX_CONCURRENT

logger = structlog.get_logger()


# Hard outer timeout for a single fetch_page call. Larger than the sum of
# inner Playwright timeouts (goto 30s + networkidle 10s + selectors up to
# ~35s + extraction) so it only fires when the browser is genuinely wedged.
FETCH_TIMEOUT = 180.0

# Periodic browser-recycle threshold. Chromium accumulates memory over long
# crawls even without crashes (DOM, IPC channels, V8 heaps). Recycling on a
# cadence bounds resident memory; an observed large doc-site crawl (~1,000 pages) used to
# peg the 3 GiB container.
RECYCLE_EVERY_PAGES = 100

# Per-close subcall timeout. A crashed browser context can make close()
# itself hang forever; cap each step.
CLOSE_STEP_TIMEOUT = 10.0

# Error fragments that mean the browser process or context is dead — not
# just a per-URL navigation failure. When seen, the browser must be torn
# down and relaunched before the next fetch can succeed.
_BROWSER_DEAD_MARKERS = (
    "target crashed",
    "target page, context or browser has been closed",
    "browser has been closed",
    "browser context has been closed",
    "browser closed",
    "connection closed",
    "session closed",
    "no target with given id",
    "browsertype.connect",
    "targetclosederror",
)


def _is_browser_dead_error(msg: str) -> bool:
    low = msg.lower()
    return any(m in low for m in _BROWSER_DEAD_MARKERS)


class BrowserManager:
    """Manages Playwright browser instance with stealth settings."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT)
        self._recycle_lock = asyncio.Lock()
        # Separate lock for browser launch — if multiple fetches enter
        # ensure_browser concurrently after a recycle, only one should run
        # the playwright.start()/chromium.launch() path. Without this, each
        # caller launches its own Chromium and only the last is kept in
        # self._browser; the rest leak as orphan processes.
        self._launch_lock = asyncio.Lock()
        self._pages_since_recycle = 0
        self._needs_recycle = False

    async def ensure_browser(self):
        """Ensure browser is running."""
        if self._browser is not None:
            return
        async with self._launch_lock:
            # Re-check under lock; another caller may have launched while we waited.
            if self._browser is not None:
                return
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            # Launch browser with stealth settings
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                ]
            )

            # Create context with realistic browser fingerprint
            self._context = await self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                locale='en-US',
                timezone_id='America/New_York',
                extra_http_headers={
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Cache-Control': 'max-age=0',
                }
            )

            # SSRF interceptor (#50): validate every request URL — including
            # redirect targets, subresources, XHR, and framesets — before the
            # browser is allowed to fetch it. Without this, a Playwright
            # navigation that starts at attacker.com (which passes our
            # pre-flight validation) could 302 to 127.0.0.1:5432 and reach an
            # internal service, since page.goto follows redirects by default.
            await self._context.route("**/*", self._ssrf_route_guard)

            # Add stealth scripts to evade detection
            await self._context.add_init_script("""
                // Overwrite navigator.webdriver
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });

                // Overwrite chrome runtime
                window.chrome = {
                    runtime: {},
                };

                // Overwrite permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications' ?
                        Promise.resolve({ state: Notification.permission }) :
                        originalQuery(parameters)
                );

                // Overwrite plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });

                // Overwrite languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en'],
                });
            """)

    async def _ssrf_route_guard(self, route) -> None:
        """Validate every http(s) request URL the browser is about to fetch (#50).

        Registered globally on the BrowserContext, so it intercepts the
        initial navigation, every redirect hop, all subresources (images,
        fonts, scripts), and any XHR/fetch the page issues. Unsafe http(s)
        URLs are aborted.

        Non-http(s) schemes (data:, blob:, about:, chrome-extension:, ...)
        bypass the SSRF check — they are not network fetches against
        attacker-controlled hosts, and validate_url would reject them on
        scheme grounds, breaking Playwright's internal page bootstrap.
        """
        url = route.request.url
        scheme_end = url.find(":")
        scheme = url[:scheme_end].lower() if scheme_end > 0 else ""
        if scheme in ("http", "https") and validate_url_safe(url) is None:
            logger.warning(
                "ssrf_route_guard blocked request",
                url=url,
                resource_type=route.request.resource_type,
            )
            try:
                await route.abort()
            except Exception as e:
                # If the browser tore down between validation and abort,
                # swallow the error — the failed fetch is the desired outcome.
                logger.debug("route.abort raised after browser teardown", error=str(e)[:200])
            return
        try:
            await route.continue_()
        except Exception as e:
            logger.debug("route.continue_ raised", url=url, error=str(e)[:200])

    async def _close_step(self, coro, name: str):
        """Run a single close subcall with a timeout, swallowing errors.

        A crashed context can make these calls hang indefinitely; cap each
        one so close() always returns in bounded time.
        """
        try:
            await asyncio.wait_for(coro, timeout=CLOSE_STEP_TIMEOUT)
        except asyncio.TimeoutError:
            logger.warning("close step timed out", step=name, timeout=CLOSE_STEP_TIMEOUT)
        except Exception as e:
            logger.warning("close step raised", step=name, error=str(e)[:200])

    async def _close_internal(self):
        """Tear down playwright/browser/context (must be called under recycle_lock).

        Nullifies each instance var *before* awaiting its close, so an outer
        cancellation (e.g. asyncio.wait_for timeout firing mid-close) can't
        leave a dangling reference that future fetches would mistake for a
        live object.
        """
        ctx = self._context
        self._context = None
        if ctx is not None:
            await self._close_step(ctx.close(), "context")

        browser = self._browser
        self._browser = None
        if browser is not None:
            await self._close_step(browser.close(), "browser")

        pw = self._playwright
        self._playwright = None
        if pw is not None:
            await self._close_step(pw.stop(), "playwright")

    async def close(self):
        """Close the browser."""
        async with self._recycle_lock:
            await self._close_internal()
            self._pages_since_recycle = 0
            self._needs_recycle = False

    async def _drain_and_recycle(self, reason: str):
        """Drain in-flight fetches via the semaphore, then recycle the browser.

        Acquiring all permits guarantees no other fetch is mid-execution
        before we tear the browser down.
        """
        async with self._recycle_lock:
            # Re-check under lock — another caller may have already recycled.
            if not self._needs_recycle and self._pages_since_recycle < RECYCLE_EVERY_PAGES:
                return

            acquired = 0
            try:
                for _ in range(MAX_CONCURRENT):
                    await self._semaphore.acquire()
                    acquired += 1
                logger.info(
                    "recycling browser",
                    reason=reason,
                    pages_since_recycle=self._pages_since_recycle,
                )
                await self._close_internal()
                self._pages_since_recycle = 0
                self._needs_recycle = False
            finally:
                for _ in range(acquired):
                    self._semaphore.release()

    async def fetch_page(self, url: str) -> tuple[Optional[BeautifulSoup], Optional[str]]:
        """Fetch a page using Playwright and return parsed soup and any error.

        Wrapped in a hard outer timeout and crash-recycle logic so a wedged
        or crashed Chromium can't freeze the indexer indefinitely.
        """
        # Pre-flight SSRF check (#50). The context-level route guard catches
        # redirects + subresources; this catches the initial URL too, with a
        # specific error message rather than relying on goto failing.
        try:
            validate_url(url)
        except ValueError as e:
            logger.warning("fetch_page blocked unsafe URL", url=url, error=str(e))
            return None, f"Blocked by SSRF policy: {e}"

        # Pre-fetch: recycle if a previous call flagged a crash or if we've
        # hit the periodic threshold.
        if self._needs_recycle:
            await self._drain_and_recycle("crash flagged")
        elif self._pages_since_recycle >= RECYCLE_EVERY_PAGES:
            await self._drain_and_recycle("periodic threshold")

        try:
            return await asyncio.wait_for(
                self._fetch_page_inner(url),
                timeout=FETCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "fetch_page hard timeout, flagging browser for recycle",
                url=url,
                timeout_sec=FETCH_TIMEOUT,
            )
            self._needs_recycle = True
            fallback_soup, _ = await self._httpx_fallback(url)
            if fallback_soup is not None:
                return fallback_soup, None
            return None, f"Timeout (>{int(FETCH_TIMEOUT)}s)"

    async def _fetch_page_inner(self, url: str) -> tuple[Optional[BeautifulSoup], Optional[str]]:
        async with self._semaphore:
            # Re-check the recycle flag after acquiring the semaphore — if
            # another fetch crashed the browser while we were blocked, the
            # context is already dead. Returning a benign failure lets the
            # next fetch_page entry run the drain+recycle path before trying
            # again, instead of guaranteed-failing on the corpse.
            if self._needs_recycle:
                return None, "Browser pending recycle (crash in concurrent fetch)"
            try:
                await self.ensure_browser()

                page = await self._context.new_page()

                try:
                    # Wait for DOM parse rather than network idle — many large vendor
                    # doc sites load analytics beacons that
                    # keep the network perpetually busy and would otherwise
                    # exhaust the timeout on every request.
                    response = await page.goto(
                        url,
                        timeout=REQUEST_TIMEOUT,
                        wait_until='domcontentloaded'
                    )

                    if response is None:
                        return None, "No response received"

                    if response.status >= 400:
                        return None, f"HTTP {response.status}"

                    # Check content type
                    content_type = response.headers.get('content-type', '')
                    if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                        return None, f"Not HTML: {content_type}"

                    # Wait for network to settle after DOM parse — many JS-heavy
                    # sites (e-commerce, forums) hydrate content via XHR after
                    # DOMContentLoaded. networkidle gives them up to 10 s to
                    # finish. Long-polling/analytics-heavy sites never reach
                    # idle; the except clause absorbs those timeouts so they
                    # fall through to the content selectors below instead of
                    # failing the whole fetch.
                    try:
                        await page.wait_for_load_state('networkidle', timeout=10000)
                    except Exception:
                        # networkidle never reached (long-polling, analytics beacons, etc.)
                        # Continue — content selectors + asyncio.sleep fallback below
                        # handle truly empty pages downstream.
                        pass

                    # Wait for JavaScript-rendered content to appear
                    content_selectors = [
                        'main',
                        'article',
                        '[role="main"]',
                        '.content',
                        '#content',
                        '.main-content',
                        '#main-content',
                    ]

                    content_found = False
                    for selector in content_selectors:
                        try:
                            await page.wait_for_selector(
                                selector,
                                state='attached',
                                timeout=5000
                            )
                            # Check for content including Shadow DOM
                            has_content = await page.evaluate(f'''
                                () => {{
                                    const el = document.querySelector('{selector}');
                                    if (!el) return false;
                                    const regularText = el.innerText || '';
                                    if (regularText.trim().length > 50) return true;
                                    function getShadowText(node) {{
                                        let text = '';
                                        if (node.shadowRoot) {{
                                            text += getShadowText(node.shadowRoot);
                                        }}
                                        for (const child of node.childNodes) {{
                                            if (child.nodeType === 3) text += child.textContent;
                                            else if (child.nodeType === 1) text += getShadowText(child);
                                        }}
                                        return text;
                                    }}
                                    const shadowText = getShadowText(el);
                                    return shadowText.trim().length > 50;
                                }}
                            ''')
                            if has_content:
                                content_found = True
                                logger.debug("Found content", url=url, selector=selector)
                                break
                        except Exception:
                            continue

                    # If no content selector worked, wait longer for any dynamic content
                    if not content_found:
                        logger.debug("No content selector matched, waiting for body content", url=url)
                        await asyncio.sleep(3.0)

                    # Extract text content including Shadow DOM using JavaScript
                    extracted_text = await page.evaluate('''
                        () => {
                            function extractText(node, depth = 0) {
                                if (depth > 50) return '';
                                let text = '';

                                if (node.nodeType === 1) {
                                    const tagName = node.tagName?.toLowerCase();
                                    if (['script', 'style', 'nav', 'header', 'footer', 'noscript', 'svg', 'path'].includes(tagName)) {
                                        return '';
                                    }
                                }

                                if (node.shadowRoot) {
                                    text += extractText(node.shadowRoot, depth + 1);
                                }

                                for (const child of (node.childNodes || [])) {
                                    if (child.nodeType === 3) {
                                        const content = child.textContent?.trim();
                                        if (content) text += content + ' ';
                                    } else if (child.nodeType === 1) {
                                        text += extractText(child, depth + 1);
                                        const display = window.getComputedStyle?.(child)?.display;
                                        if (['block', 'flex', 'grid', 'table'].includes(display)) {
                                            text += '\\n';
                                        }
                                    }
                                }

                                return text;
                            }

                            const contentSelectors = ['main', 'article', '[role="main"]', '.content', '#content'];
                            for (const sel of contentSelectors) {
                                const el = document.querySelector(sel);
                                if (el) {
                                    const text = extractText(el);
                                    if (text.trim().length > 100) {
                                        return text;
                                    }
                                }
                            }

                            return extractText(document.body);
                        }
                    ''')

                    # Get the rendered HTML content for title extraction
                    html_content = await page.content()
                    soup = BeautifulSoup(html_content, 'html.parser')

                    # Store extracted text in a custom attribute for later use
                    soup._shadow_dom_text = extracted_text

                    # Rate limiting delay
                    await asyncio.sleep(REQUEST_DELAY)

                    self._pages_since_recycle += 1
                    return soup, None

                finally:
                    # page.close() on a crashed target can itself raise; we
                    # don't care — the recycle path will replace the context.
                    try:
                        await asyncio.wait_for(page.close(), timeout=CLOSE_STEP_TIMEOUT)
                    except Exception:
                        pass

            except Exception as e:
                error_msg = str(e)
                if _is_browser_dead_error(error_msg):
                    self._needs_recycle = True
                    logger.warning(
                        "browser crash detected, scheduling recycle",
                        url=url,
                        error=error_msg[:300],
                    )
                else:
                    # Still count failed pages toward periodic recycle so a
                    # sustained-failure crawl doesn't leak indefinitely.
                    self._pages_since_recycle += 1
                # Try httpx fallback for cases where Playwright fails
                # (browser context crashes, navigation errors). Works for any
                # server-rendered site that returns full HTML in the initial
                # response.
                fallback_soup, fallback_err = await self._httpx_fallback(url)
                if fallback_soup is not None:
                    logger.info(
                        "Playwright failed, httpx fallback succeeded",
                        url=url,
                        playwright_error=error_msg[:200],
                    )
                    return fallback_soup, None
                # Simplify common error messages
                if 'Timeout' in error_msg:
                    return None, "Timeout"
                return None, error_msg

    async def _httpx_fallback(self, url: str) -> tuple[Optional[BeautifulSoup], Optional[str]]:
        """Static HTTP fetch fallback for when Playwright fails.

        Redirects are followed manually (not by httpx) so each hop's
        destination is validated against the SSRF policy before the next
        request. Previously, follow_redirects=True could let attacker.com
        302 to 127.0.0.1 and reach internal services (#50).
        """
        max_hops = 5
        current = url
        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                follow_redirects=False,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                },
            ) as client:
                for hop in range(max_hops):
                    # Validate every hop, including the initial URL. The
                    # caller validated the entry URL too, but cheap to re-do
                    # and required for redirect targets discovered here.
                    if validate_url_safe(current) is None:
                        logger.warning(
                            "httpx_fallback blocked unsafe URL",
                            url=current,
                            hop=hop,
                        )
                        return None, "Blocked by SSRF policy"
                    response = await client.get(current)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            return None, f"HTTP {response.status_code} with no Location header"
                        # urljoin handles relative redirects ("/path") and absolute ones.
                        from urllib.parse import urljoin
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        return None, f"HTTP {response.status_code}"
                    content_type = response.headers.get('content-type', '')
                    if 'text/html' not in content_type and 'application/xhtml' not in content_type:
                        return None, f"Not HTML: {content_type}"
                    soup = BeautifulSoup(response.text, 'html.parser')
                    return soup, None
                return None, f"Too many redirects (>{max_hops})"
        except Exception as e:
            return None, str(e)
