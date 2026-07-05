"""
Data classes for the ingestion service.

Contains all dataclasses used across ingestion operations.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class SiteTreeNode:
    """Node in the site tree structure."""
    url: str
    title: str
    path: str
    children: list['SiteTreeNode']


@dataclass
class ScanResult:
    """Result from URL scan."""
    tree: SiteTreeNode
    sitemap_url: Optional[str] = None


@dataclass
class IndexingStatus:
    """Status of an indexing operation."""
    source_id: str
    status: str
    progress: int
    progress_total: int
    progress_message: Optional[str]
    document_count: int
    chunk_count: int
    error_message: Optional[str]


@dataclass
class IndexingLogEntry:
    """A single indexing log entry."""
    id: str
    source_id: str
    url: str
    status: str
    error_message: Optional[str]
    scrape_duration_ms: Optional[int]
    embed_duration_ms: Optional[int]
    content_length: Optional[int]
    chunk_count: Optional[int]
    created_at: datetime
    updated_at: datetime


@dataclass
class IndexingLogSummary:
    """Summary of indexing logs."""
    logs: list[IndexingLogEntry]
    total: int
    done: int
    failed: int
    skipped: int
    pending: int
    in_progress: int
