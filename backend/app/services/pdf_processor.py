"""
PDF processing module for extracting text from PDF files.

Uses pypdf to read PDF files and extract text content for indexing.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pypdf import PdfReader

logger = logging.getLogger(__name__)


@dataclass
class PDFContent:
    """Extracted content and metadata from a PDF file."""
    text: str
    page_count: int
    title: Optional[str] = None
    author: Optional[str] = None
    subject: Optional[str] = None
    file_size_bytes: int = 0


class PDFProcessingError(Exception):
    """Raised when PDF processing fails."""
    pass


def extract_pdf_content(file_path: str) -> PDFContent:
    """
    Extract text content and metadata from a PDF file.

    Args:
        file_path: Path to the PDF file

    Returns:
        PDFContent with extracted text and metadata

    Raises:
        PDFProcessingError: If the file cannot be read or processed
    """
    path = Path(file_path)

    if not path.exists():
        raise PDFProcessingError(f"File not found: {file_path}")

    if not path.suffix.lower() == ".pdf":
        raise PDFProcessingError(f"Not a PDF file: {file_path}")

    try:
        file_size = path.stat().st_size
        reader = PdfReader(str(path))

        # Extract metadata
        metadata = reader.metadata or {}
        title = metadata.get("/Title")
        author = metadata.get("/Author")
        subject = metadata.get("/Subject")

        # Extract text from all pages
        text_parts = []
        for page_num, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- Page {page_num} ---\n{page_text}")
            except Exception as e:
                logger.warning(f"Failed to extract text from page {page_num}: {e}")
                text_parts.append(f"--- Page {page_num} ---\n[Text extraction failed]")

        full_text = "\n\n".join(text_parts)

        if not full_text.strip():
            raise PDFProcessingError(
                "No text content could be extracted from the PDF. "
                "The file may be image-based or encrypted."
            )

        return PDFContent(
            text=full_text,
            page_count=len(reader.pages),
            title=title,
            author=author,
            subject=subject,
            file_size_bytes=file_size,
        )

    except PDFProcessingError:
        raise
    except Exception as e:
        logger.exception(f"Error processing PDF {file_path}")
        raise PDFProcessingError(f"Failed to process PDF: {str(e)}")
