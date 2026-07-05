"""
Tests for ``app.services.web_scraper.parser.extract_content``.

Specifically covers the regression fixed in #105: when the priority selector
matches a container that has near-empty text (e.g. vBulletin-style
``<div id="content">`` that wraps only nav/sidebar), the function used to
return that empty string and the URL indexer would silently produce 0 chunks.
The fix falls back to ``<body>`` when the selected container is too short.
"""
from bs4 import BeautifulSoup

from app.services.web_scraper.parser import extract_content


def _make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


class TestExtractContentFallback:
    def test_returns_body_text_when_main_container_is_empty(self):
        """Regression for #105.

        The priority selector matches ``<div id="content">`` first; that div
        is empty. ``<body>`` carries the real article text. Before the fix
        this returned an empty string; now it should return the body text.
        """
        html = """
        <html>
          <body>
            <div id="content"></div>
            <div class="postcontent">
              This is the actual article body. It has enough text to be
              considered useful by the extractor's minimum-length threshold,
              well over fifty characters in total.
            </div>
          </body>
        </html>
        """
        text = extract_content(_make_soup(html))
        assert "actual article body" in text
        # And it should NOT be empty
        assert len(text.strip()) > 50

    def test_uses_main_container_when_it_has_real_text(self):
        """Happy path: when the selected container has useful text, use it."""
        html = """
        <html>
          <body>
            <main>
              The main element contains the real content here. This text is
              long enough to clear the minimum-length threshold easily.
            </main>
            <aside>Sidebar noise that should be excluded.</aside>
          </body>
        </html>
        """
        text = extract_content(_make_soup(html))
        assert "real content" in text
        assert "Sidebar noise" not in text

    def test_handles_completely_empty_body(self):
        """Empty body should return empty string, not crash."""
        html = "<html><body></body></html>"
        text = extract_content(_make_soup(html))
        assert text == ""

    def test_no_body_at_all(self):
        """Soup without a body tag should not crash."""
        html = "<div>Some loose div content that's long enough to be useful here.</div>"
        text = extract_content(_make_soup(html))
        assert "loose div content" in text
