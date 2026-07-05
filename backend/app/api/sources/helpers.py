"""
Helper functions for Sources API.

Response conversion utilities used across multiple endpoints.
"""
import json as json_lib
from typing import Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentContent, Source
from app.services.freshness_service import get_freshness_status

from .schemas import (
    SourceResponse,
    SiteTreeNode,
    ProjectInfo,
    AgentInfo,
    FileInfo,
)


async def get_sub_source_counts(
    db: AsyncSession, parent_ids: list[str]
) -> dict[str, int]:
    """Return {parent_source_id: child_count} for the given root ids.

    Returns 0 for any id without children. Empty input → empty dict.
    """
    if not parent_ids:
        return {}
    stmt = (
        select(Source.parent_source_id, func.count(Source.id))
        .where(Source.parent_source_id.in_(parent_ids))
        .group_by(Source.parent_source_id)
    )
    rows = (await db.execute(stmt)).all()
    counts = {pid: 0 for pid in parent_ids}
    for parent_id, count in rows:
        counts[parent_id] = count
    return counts

def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so a literal path prefix isn't treated as a pattern."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def get_sub_source_document_counts(
    db: AsyncSession, sources: list
) -> dict[str, int]:
    """Return {sub_source_id: document_count} derived from the parent's docs.

    Sub-sources are filtered views over a parent root and are never indexed on
    their own, so their stored ``document_count`` is always 0. The real count is
    the number of the PARENT's document_content rows whose path falls under the
    sub-source's ``path_prefix``. Non-sub-sources (no parent / no prefix) are
    omitted from the result.

    Prefix matching is segment-aware: ``/data/documents/Alpha`` matches
    ``/data/documents/Alpha/x.pdf`` but NOT ``/data/documents/AlphaBeta/y.pdf``.

    All counts are computed in a single query using per-sub-source conditional
    aggregation (``COUNT(*) FILTER (WHERE ...)``) to avoid an N+1 pattern. Note
    we cannot fan out with asyncio.gather here — a single AsyncSession holds one
    connection and rejects concurrent execute() calls.
    """
    sub_sources = [
        s for s in sources
        if getattr(s, "parent_source_id", None) and getattr(s, "path_prefix", None)
    ]
    if not sub_sources:
        return {}

    parent_ids = {s.parent_source_id for s in sub_sources}
    columns = []
    for i, s in enumerate(sub_sources):
        base = s.path_prefix.rstrip("/")
        like_pattern = _escape_like(base) + "/%"
        condition = and_(
            DocumentContent.source_id == s.parent_source_id,
            or_(
                DocumentContent.url == base,
                DocumentContent.url.like(like_pattern, escape="\\"),
            ),
        )
        columns.append(func.count().filter(condition).label(f"c{i}"))

    stmt = select(*columns).where(DocumentContent.source_id.in_(parent_ids))
    row = (await db.execute(stmt)).one()
    return {s.id: (row[i] or 0) for i, s in enumerate(sub_sources)}


async def get_sub_source_chunk_counts(
    db: AsyncSession, sources: list
) -> dict[str, int]:
    """Return {sub_source_id: chunk_count} derived from the parent's documents.

    Like ``document_count``, a sub-source's stored ``chunk_count`` is always 0 —
    it owns no chunks, only a filtered view over its parent root's content. The
    real count is the sum of the PARENT's per-document ``chunk_count`` values
    (``documents`` table) whose ``file_path`` falls under the sub-source's
    ``path_prefix``. This mirrors get_sub_source_document_counts (same segment-
    aware prefix match, same single-query conditional aggregation) but summing
    chunk counts instead of counting rows.

    A Postgres sum is used rather than a live Qdrant count because the chunks for
    a directory source physically live wherever it was indexed (e.g. a library's
    collection for library-bound sources), so the source's own ``collection_name``
    is not a reliable handle. The per-document ``chunk_count`` recorded at index
    time is the authoritative, collection-agnostic figure. Documents are first
    de-duplicated per ``(source_id, file_path)`` so a source bound to multiple
    libraries does not multiply the count.

    Non-sub-sources are omitted. Sources without per-document records (e.g. a
    directory source that was never library-indexed) yield 0 — the same as the
    prior behaviour, never worse.
    """
    sub_sources = [
        s for s in sources
        if getattr(s, "parent_source_id", None) and getattr(s, "path_prefix", None)
    ]
    if not sub_sources:
        return {}

    parent_ids = {s.parent_source_id for s in sub_sources}

    # One chunk_count per (source_id, file_path): collapses multi-library
    # duplicates so the sum reflects the source's documents, not its bindings.
    per_doc = (
        select(
            Document.source_id.label("sid"),
            Document.file_path.label("fp"),
            func.max(Document.chunk_count).label("cc"),
        )
        .where(Document.source_id.in_(parent_ids))
        .group_by(Document.source_id, Document.file_path)
        .subquery()
    )

    columns = []
    for i, s in enumerate(sub_sources):
        base = s.path_prefix.rstrip("/")
        like_pattern = _escape_like(base) + "/%"
        condition = and_(
            per_doc.c.sid == s.parent_source_id,
            or_(
                per_doc.c.fp == base,
                per_doc.c.fp.like(like_pattern, escape="\\"),
            ),
        )
        columns.append(func.sum(per_doc.c.cc).filter(condition).label(f"c{i}"))

    stmt = select(*columns).select_from(per_doc)
    row = (await db.execute(stmt)).one()
    return {s.id: (row[i] or 0) for i, s in enumerate(sub_sources)}


# Backward-compatible alias
KnowledgeSourceResponse = SourceResponse

# Keys in the description JSON blob that hold secrets and must never be
# returned to API callers.  Values are replaced with a fixed redaction marker.
_REDACTED_MARKER = "[REDACTED]"
_DESCRIPTION_SECRET_KEYS = {"github_token", "token", "api_key", "password", "secret"}


def _redact_description(description: Optional[str]) -> Optional[str]:
    """Redact secret keys from the description JSON blob.

    The description field for GitHub/URL sources is a JSON object that may
    include a 'github_token' key.  Strip those values before returning the
    response so tokens are never exposed over the API.

    Non-JSON descriptions (plain strings) are returned unchanged.
    """
    if not description:
        return description
    if not description.startswith("{"):
        return description
    try:
        data = json_lib.loads(description)
    except json_lib.JSONDecodeError:
        return description

    redacted = False
    for key in _DESCRIPTION_SECRET_KEYS:
        if key in data and data[key]:
            data[key] = _REDACTED_MARKER
            redacted = True

    return json_lib.dumps(data) if redacted else description


def source_to_response(
    source,
    assigned_projects: Optional[list[ProjectInfo]] = None,
    owner_project: Optional[ProjectInfo] = None,
    bound_agents: Optional[list[AgentInfo]] = None,
    sub_source_count: int = 0,
    document_count_override: Optional[int] = None,
    chunk_count_override: Optional[int] = None,
) -> SourceResponse:
    """Convert a KnowledgeSource model to API response.

    ``document_count_override`` and ``chunk_count_override`` are used for
    sub-sources, whose stored ``document_count``/``chunk_count`` are always 0 —
    see get_sub_source_document_counts and get_sub_source_chunk_counts.
    """
    selected_urls = None
    if source.selected_urls:
        try:
            selected_urls = json_lib.loads(source.selected_urls)
        except (json_lib.JSONDecodeError, TypeError):
            pass

    selected_files = None
    if source.selected_files:
        try:
            files_data = json_lib.loads(source.selected_files)
            selected_files = [
                FileInfo(
                    path=f["path"],
                    original_name=f.get("original_name", ""),
                    size_bytes=f.get("size_bytes", 0)
                )
                for f in files_data
            ]
        except (json_lib.JSONDecodeError, TypeError, KeyError):
            pass

    return SourceResponse(
        id=source.id,
        name=source.name,
        description=_redact_description(source.description),
        source_type=source.source_type,
        source_path=source.source_path,
        project_id=source.project_id,
        status=source.status,
        last_indexed=source.last_indexed,
        document_count=(
            document_count_override
            if document_count_override is not None
            else source.document_count
        ),
        chunk_count=(
            chunk_count_override
            if chunk_count_override is not None
            else source.chunk_count
        ),
        error_message=source.error_message,
        progress=source.progress,
        progress_total=source.progress_total,
        progress_message=source.progress_message,
        progress_updated_at=source.progress_updated_at,
        created_at=source.created_at,
        selected_urls=selected_urls,
        selected_files=selected_files,
        collection_name=source.collection_name,
        embedding_provider=source.embedding_provider,
        embedding_model=source.embedding_model,
        embedding_dimensions=source.embedding_dimensions,
        assigned_projects=assigned_projects or [],
        owner_project=owner_project,
        bound_agents=bound_agents or [],
        enrichment_enabled=source.enrichment_enabled,
        enrichment_taxonomy_id=source.enrichment_taxonomy_id,
        enrichment_model=source.enrichment_model,
        watch_enabled=source.watch_enabled,
        watch_extensions=source.watch_extensions,
        watch_mode=source.watch_mode,
        watch_poll_interval_seconds=source.watch_poll_interval_seconds,
        watch_debounce_seconds=source.watch_debounce_seconds,
        watch_max_file_size_mb=source.watch_max_file_size_mb,
        watch_depth=source.watch_depth,
        watch_status=source.watch_status,
        watch_last_heartbeat_at=source.watch_last_heartbeat_at,
        watch_last_error=source.watch_last_error,
        freshness_policy=source.freshness_policy,
        stale_after_days=source.stale_after_days,
        refresh_interval_days=source.refresh_interval_days,
        next_refresh_at=source.next_refresh_at,
        freshness_status=get_freshness_status(source),
        youtube_backfill_mode=getattr(source, "youtube_backfill_mode", None),
        youtube_recent_count=getattr(source, "youtube_recent_count", None),
        parent_source_id=getattr(source, "parent_source_id", None),
        path_prefix=getattr(source, "path_prefix", None),
        path_excludes=getattr(source, "path_excludes", None),
        sub_source_count=sub_source_count,
    )


def tree_to_response(node) -> SiteTreeNode:
    """Convert a SiteTreeNode dataclass to Pydantic model."""
    return SiteTreeNode(
        url=node.url,
        title=node.title,
        path=node.path,
        children=[tree_to_response(child) for child in node.children],
    )
