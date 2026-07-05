"""
Indexer implementations for different source types.

Each indexer handles the specifics of indexing a particular content type:
- DirectoryIndexer: Local directories of text/markdown files
- FileIndexer: PDF, PPTX, DOCX, TXT, MD (with Tika + enrichment support)
- UrlIndexer: Web pages via URL scraping
- tika: Tika extraction helper (extract_text_with_tika)

GitHub source ingestion was removed in #104 (the indexer was never wired into
the KB-aware Document pipeline and had no live sources). If GitHub ingestion
returns in the future, prefer building it on top of UrlIndexer + a repo-tree
expander rather than maintaining a parallel indexer.
"""
from .base import BaseIndexer
from .directory import DirectoryIndexer
from .file import FileIndexer
from .file_item import FileItemIndexer
from .url import UrlIndexer
from .youtube import YouTubeIndexer
from .tika import extract_text_with_tika, TIKA_SUPPORTED_EXTENSIONS

__all__ = [
    "BaseIndexer",
    "DirectoryIndexer",
    "FileIndexer",
    "FileItemIndexer",
    "UrlIndexer",
    "YouTubeIndexer",
    "extract_text_with_tika",
    "TIKA_SUPPORTED_EXTENSIONS",
]
