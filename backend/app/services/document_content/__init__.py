"""
DocumentContent service package.

Manages raw document storage for re-embedding without re-scraping.
Supports web (URL-keyed), file upload, and directory-sourced documents.

Usage:
    from app.services.document_content import DocumentContentService
"""
from .service import DocumentContentService

__all__ = ["DocumentContentService"]
