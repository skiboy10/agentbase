"""
HTML content parsing utilities.

Extracts titles, content, and links from HTML pages.
"""

import re
from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup


def normalize_url(url: str) -> str:
    """Normalize URL by removing fragments and trailing slashes."""
    parsed = urlparse(url)
    # Remove fragment
    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path.rstrip('/') or '/',
        parsed.params,
        parsed.query,
        ''  # Remove fragment
    ))
    return normalized


def get_path_prefix(url: str) -> str:
    """Extract the path prefix from a URL for filtering."""
    parsed = urlparse(url)
    path = parsed.path

    # Get the directory path (remove filename if present)
    if '.' in path.split('/')[-1]:
        # Has file extension, get parent directory
        path = '/'.join(path.split('/')[:-1])

    return path.rstrip('/') or '/'


def is_valid_link(href: str, base_url: str, path_prefix: str) -> bool:
    """Check if a link should be followed."""
    if not href:
        return False

    # Skip non-http links
    if href.startswith(('javascript:', 'mailto:', 'tel:', '#', 'data:')):
        return False

    # Skip common non-page extensions
    skip_extensions = (
        '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico',
        '.css', '.js', '.json', '.xml', '.zip', '.tar', '.gz',
        '.mp4', '.mp3', '.wav', '.avi', '.mov'
    )
    if any(href.lower().endswith(ext) for ext in skip_extensions):
        return False

    # Resolve relative URL
    full_url = urljoin(base_url, href)
    parsed = urlparse(full_url)
    base_parsed = urlparse(base_url)

    # Must be same domain
    if parsed.netloc != base_parsed.netloc:
        return False

    # Must be within path prefix
    if not parsed.path.startswith(path_prefix):
        return False

    return True


def extract_links(soup: BeautifulSoup, base_url: str, path_prefix: str) -> list[str]:
    """Extract valid links from a page, prioritizing navigation elements."""
    links = []
    seen = set()

    # First, try to find navigation/sidebar elements (common in docs sites)
    nav_selectors = [
        ('nav', {}),
        ('aside', {}),
        ('div', {'class': re.compile(r'sidebar|nav|menu|toc|navigation', re.I)}),
        ('div', {'id': re.compile(r'sidebar|nav|menu|toc|navigation', re.I)}),
        ('ul', {'class': re.compile(r'nav|menu|toc', re.I)}),
        ('div', {'role': 'navigation'}),
    ]

    # Collect links from navigation elements first
    for tag, attrs in nav_selectors:
        nav_elements = soup.find_all(tag, attrs)
        for nav_elem in nav_elements:
            for a_tag in nav_elem.find_all('a', href=True):
                href = a_tag['href']
                if not is_valid_link(href, base_url, path_prefix):
                    continue
                full_url = normalize_url(urljoin(base_url, href))
                if full_url not in seen:
                    seen.add(full_url)
                    links.append(full_url)

    # Then collect all other links from the page
    for a_tag in soup.find_all('a', href=True):
        href = a_tag['href']

        if not is_valid_link(href, base_url, path_prefix):
            continue

        full_url = normalize_url(urljoin(base_url, href))

        if full_url not in seen:
            seen.add(full_url)
            links.append(full_url)

    return links


def extract_title(soup: BeautifulSoup) -> str:
    """Extract page title from HTML."""
    # Try <title> tag first
    if soup.title and soup.title.string:
        return soup.title.string.strip()

    # Try <h1> tag
    h1 = soup.find('h1')
    if h1:
        return h1.get_text(strip=True)

    # Try first heading
    for tag in ['h2', 'h3']:
        heading = soup.find(tag)
        if heading:
            return heading.get_text(strip=True)

    return "Untitled"


def extract_code_blocks(soup: BeautifulSoup) -> list[dict]:
    """Extract code blocks from HTML with language detection.

    Returns list of code blocks with structure:
    {
        'content': str,
        'language': str,
        'type': 'code' | 'pre',
        'has_language_class': bool
    }
    """
    code_blocks = []

    # Find all <pre> and <code> tags
    for tag in soup.find_all(['pre', 'code']):
        # Skip if already processed (nested tags)
        if hasattr(tag, '_processed'):
            continue

        # Extract content
        content = tag.get_text(strip=True)

        # Skip empty blocks
        if not content or len(content) < 5:
            continue

        # Detect language from class attribute
        language = 'unknown'
        has_language_class = False

        if tag.get('class'):
            classes = tag.get('class')
            for cls in classes:
                # Common patterns: language-python, lang-python, python, brush-python
                if cls.startswith(('language-', 'lang-', 'brush-')):
                    language = cls.split('-', 1)[1]
                    has_language_class = True
                    break
                # Direct language class (python, javascript, etc.)
                elif cls.lower() in [
                    'python', 'javascript', 'java', 'cpp', 'c', 'csharp', 'ruby',
                    'go', 'rust', 'php', 'swift', 'kotlin', 'typescript', 'sql',
                    'html', 'css', 'bash', 'shell', 'powershell', 'yaml', 'json',
                    'xml', 'markdown', 'ampscript', 'ssjs', 'amp'
                ]:
                    language = cls.lower()
                    has_language_class = True
                    break

        # Check data-lang attribute (alternative pattern)
        if not has_language_class and tag.get('data-lang'):
            language = tag.get('data-lang')
            has_language_class = True

        # Special case: if inside <pre> without language, check child <code>
        if tag.name == 'pre' and not has_language_class:
            code_child = tag.find('code')
            if code_child and code_child.get('class'):
                classes = code_child.get('class')
                for cls in classes:
                    if cls.startswith(('language-', 'lang-', 'brush-')):
                        language = cls.split('-', 1)[1]
                        has_language_class = True
                        break

        # Check parent elements for language class (e.g., <div class="highlight-python3"><pre>)
        if not has_language_class and tag.parent:
            parent = tag.parent
            # Check up to 2 levels of parents
            for _ in range(2):
                if parent and parent.get('class'):
                    parent_classes = parent.get('class')
                    for cls in parent_classes:
                        # Match patterns like "highlight-python3", "language-python", etc.
                        if cls.startswith(('highlight-', 'language-', 'lang-', 'brush-')):
                            lang_part = cls.split('-', 1)[1] if '-' in cls else cls
                            # Clean up language name (e.g., "python3" -> "python")
                            language = lang_part.rstrip('0123456789')
                            has_language_class = True
                            break
                        elif cls.lower() in [
                            'python', 'javascript', 'java', 'cpp', 'c', 'csharp', 'ruby',
                            'go', 'rust', 'php', 'swift', 'kotlin', 'typescript', 'sql',
                            'html', 'css', 'bash', 'shell', 'powershell', 'yaml', 'json',
                            'xml', 'markdown', 'ampscript', 'ssjs', 'amp'
                        ]:
                            language = cls.lower()
                            has_language_class = True
                            break
                    if has_language_class:
                        break
                parent = parent.parent if parent else None

        code_blocks.append({
            'content': content,
            'language': language,
            'type': tag.name,
            'has_language_class': has_language_class
        })

        # Mark as processed to avoid duplicates with nested tags
        tag._processed = True

    return code_blocks


def extract_content(soup: BeautifulSoup, preserve_code: bool = False) -> str | tuple[str, list[dict]]:
    """Extract main text content from HTML.

    Uses Shadow DOM extracted text if available (from browser.py),
    otherwise falls back to BeautifulSoup extraction.

    Args:
        soup: BeautifulSoup object
        preserve_code: If True, extract code blocks separately and return (text, code_blocks)

    Returns:
        If preserve_code=False: str (text content)
        If preserve_code=True: tuple (text content, list of code block dicts)
    """
    # Extract code blocks first if requested
    code_blocks = []
    if preserve_code:
        code_blocks = extract_code_blocks(soup)
    # Check if we have Shadow DOM extracted text (set by browser.py)
    shadow_text = getattr(soup, '_shadow_dom_text', None)
    if shadow_text and len(shadow_text.strip()) > 50:
        # Clean up the shadow DOM extracted text
        text = shadow_text
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    # Fall back to BeautifulSoup extraction for non-Shadow DOM pages
    # Remove unwanted elements
    for element in soup.find_all(['script', 'style', 'nav', 'header', 'footer', 'aside', 'noscript']):
        element.decompose()

    # Try to find main content area
    main_content = None

    # Priority order for content containers
    content_selectors = [
        ('main', {}),
        ('article', {}),
        ('div', {'class': re.compile(r'content|main|body|article', re.I)}),
        ('div', {'id': re.compile(r'content|main|body|article', re.I)}),
        ('div', {'role': 'main'}),
    ]

    for tag, attrs in content_selectors:
        main_content = soup.find(tag, attrs)
        if main_content:
            break

    # Fall back to body
    if not main_content:
        main_content = soup.find('body') or soup

    # Extract text
    text = main_content.get_text(separator='\n', strip=True)

    # On some templated sites (vBulletin, forums, certain CMS themes) the
    # selector above matches a container like <div id="content"> that's
    # actually just a wrapper around nav/sidebar — the real article text
    # lives elsewhere. The selector finds it, returns near-empty text, and
    # the caller silently produces 0 chunks. Detect that case and re-extract
    # from <body> so we still get something usable.
    MIN_USEFUL_LEN = 50
    if len(text) < MIN_USEFUL_LEN:
        body = soup.find('body')
        if body and body is not main_content:
            fallback_text = body.get_text(separator='\n', strip=True)
            if len(fallback_text) > len(text):
                text = fallback_text

    # Clean up excessive whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r' {2,}', ' ', text)

    text = text.strip()

    # Return text and code blocks if requested
    if preserve_code:
        return text, code_blocks

    return text
