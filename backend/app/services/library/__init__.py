"""
Library service package.

Provides CRUD and management operations for KnowledgeBase (Library) and Document entities.
"""
from .service import LibraryService, DocumentService
from .coverage import get_library_coverage

# Backward-compatible alias
KnowledgeBaseService = LibraryService

__all__ = [
    "LibraryService",
    "KnowledgeBaseService",
    "DocumentService",
    "get_library_coverage",
]
