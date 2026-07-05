"""
Tika text extraction for document files.

Sends files to Apache Tika for high-quality text extraction from
PDF, PPTX, DOCX, and other binary document formats.

Falls back gracefully to None when Tika is unavailable so callers
can use their existing extractor instead.
"""
import re
from pathlib import Path
from typing import Optional

import httpx
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()

settings = get_settings()

# File types that benefit from Tika extraction
TIKA_SUPPORTED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".ppt", ".doc", ".odt", ".odp"}

# Post-processing: remove common Tika extraction artifacts
_TIKA_ARTIFACT_RE = re.compile(
    r"(?:"
    r"Extracting pages from (?:PDF|PPTX|DOCX)[^\n]*\n?"    # Tika progress lines
    r"|(?:Created with|Produced by)\s+[^\n]*\n?"            # Tool watermarks
    r"|(?:This presentation was created)[^\n]*\n?"          # Presentation boilerplate
    r")",
    re.IGNORECASE,
)


async def extract_text_with_tika(
    file_path: str,
    tika_url: Optional[str] = None,
    timeout: Optional[int] = None,
) -> Optional[str]:
    """
    Send a file to Tika and return plain text.

    Args:
        file_path: Absolute path to the file on disk.
        tika_url: Base URL for Tika server (defaults to settings.tika_url).
        timeout: Request timeout in seconds (defaults to settings.tika_timeout / 1000).

    Returns:
        Extracted plain text, or None if Tika is unavailable or extraction fails.
        Returning None signals the caller to fall back to its existing extractor.
    """
    effective_url = tika_url or settings.tika_url
    # settings.tika_timeout is in milliseconds; httpx timeout is in seconds
    effective_timeout = timeout if timeout is not None else (settings.tika_timeout / 1000)

    path = Path(file_path)
    if not path.exists():
        logger.warning("File not found for Tika extraction", file_path=file_path)
        return None

    ext = path.suffix.lower()
    if ext not in TIKA_SUPPORTED_EXTENSIONS:
        logger.debug("File type not in Tika-supported set, skipping", ext=ext)
        return None

    try:
        file_bytes = path.read_bytes()
    except OSError as exc:
        logger.warning("Cannot read file for Tika extraction", file_path=file_path, error=str(exc))
        return None

    try:
        async with httpx.AsyncClient(timeout=effective_timeout) as client:
            response = await client.put(
                f"{effective_url}/tika",
                content=file_bytes,
                headers={
                    "Accept": "text/plain",
                    "Content-Type": "application/octet-stream",
                },
            )
            response.raise_for_status()
            raw_text = response.text

    except httpx.ConnectError:
        logger.warning("Tika server unavailable", tika_url=effective_url)
        return None
    except httpx.TimeoutException:
        logger.warning("Tika request timed out", file_path=file_path, timeout=effective_timeout)
        return None
    except httpx.HTTPStatusError as exc:
        logger.warning(
            "Tika returned HTTP error",
            file_path=file_path,
            status_code=exc.response.status_code,
        )
        return None
    except Exception as exc:
        logger.warning("Unexpected Tika error", file_path=file_path, error=str(exc))
        return None

    # Post-process: remove known Tika artifacts
    cleaned = _TIKA_ARTIFACT_RE.sub("", raw_text)
    cleaned = cleaned.strip()

    if not cleaned:
        logger.warning("Tika returned empty text", file_path=file_path)
        return None

    logger.info(
        "Tika extraction complete",
        file_path=file_path,
        original_bytes=len(raw_text),
        cleaned_bytes=len(cleaned),
    )
    return cleaned
