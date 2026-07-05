"""
Shared file-text extraction used by DirectoryIndexer, FileIndexer, and FileItemIndexer.

Centralises Tika-first extraction with pypdf fallback for PDFs and a plain
read for text/markdown, plus the unicode sanitisation that strips null bytes
and surrogates so Qdrant payloads can be encoded safely.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import structlog

from .tika import extract_text_with_tika, TIKA_SUPPORTED_EXTENSIONS

logger = structlog.get_logger()


# Extensions any of the directory/file-item paths can handle. The FileIndexer
# has its own slightly different list because it supports a handful of extras;
# this set is the common ground for tree-walking ingestion.
COMMON_TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".html", ".json"}


def sanitize_text(text: str) -> str:
    """Remove null bytes and non-encodable unicode so Qdrant accepts the payload."""
    text = text.replace("\x00", "")
    return text.encode("utf-8", errors="replace").decode("utf-8")


async def extract_file_text(file_path: Path, ext: Optional[str] = None) -> str | None:
    """
    Extract text from a file path.

    Tries Tika first for PDF/PPTX/DOCX, falls back to pypdf for PDFs, and reads
    plain text for .md/.txt/.html/.json. Returns ``None`` when nothing usable
    can be extracted (caller should treat as "skip this file").
    """
    ext = (ext or file_path.suffix).lower()

    # Binary documents — Tika first
    if ext in TIKA_SUPPORTED_EXTENSIONS:
        tika_text = await extract_text_with_tika(str(file_path))
        if tika_text:
            return sanitize_text(tika_text)

        if ext == ".pdf":
            logger.info("Tika unavailable, falling back to pypdf", file=file_path.name)
            from app.services.pdf_processor import extract_pdf_content, PDFProcessingError
            try:
                pdf_content = extract_pdf_content(str(file_path))
                return sanitize_text(pdf_content.text)
            except PDFProcessingError as e:
                logger.warning("PDF fallback failed", file=str(file_path), error=str(e))
                return None
        return None  # No fallback for non-PDF binary formats without Tika

    # Plain text / markdown / html / json
    try:
        return sanitize_text(file_path.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        try:
            return sanitize_text(file_path.read_text(encoding="latin-1"))
        except OSError as e:
            logger.warning("Cannot read file", file=str(file_path), error=str(e))
            return None
    except OSError as e:
        logger.warning("Cannot read file", file=str(file_path), error=str(e))
        return None
