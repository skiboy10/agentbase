"""
Chunk neighbor fetching and filter value discovery utilities.

fetch_chunk_neighbors: retrieves adjacent chunks from the same document to
    provide surrounding context for a matched chunk.

list_unique_field_values: samples Qdrant points to collect unique values for
    a metadata field, used by the list_filter_values MCP tool.
"""
from typing import Optional

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, Range

logger = structlog.get_logger()

# Map user-facing field names to Qdrant payload paths.
# Mirrors FILTERABLE_FIELDS in filters.py plus extra enrichment fields.
_FIELD_TO_PAYLOAD_PATH = {
    "platforms": "metadata.platforms",
    "products": "metadata.products",
    "offerings": "metadata.offerings",
    "doc_category": "metadata.doc_category",
    "companies": "metadata.companies",
    "topics": "metadata.topics",
    "document_type": "metadata.document_type",
    "file_type": "metadata.file_type",
    # Publish-date facets (discoverable distinct values). published_date is a
    # continuous int (range-filtered, not value-listed) so it is omitted here.
    "published_year": "metadata.published_year",
    "published_month": "metadata.published_month",
}

# How many points to scroll per collection when sampling filter values.
# Large enough to capture rare values; small enough to stay fast.
_SAMPLE_LIMIT = 500


async def fetch_chunk_neighbors(
    client: QdrantClient,
    collection: str,
    metadata: dict,
    chunk_index: Optional[int],
    window_size: int = 1,
) -> list[dict]:
    """
    Fetch neighboring chunks from the same document in Qdrant.

    Identifies the document using `file_id` from the chunk metadata, then
    retrieves chunks whose chunk_index falls within [chunk_index - N,
    chunk_index + N] from the same document.

    The matched chunk itself is included in the returned list so the caller
    gets a contiguous window sorted by chunk_index.

    Args:
        client: Qdrant client instance.
        collection: Collection name the source chunk came from.
        metadata: Metadata dict of the source chunk (must contain chunk_index
                  and at least one of: file_id, source_id).
        chunk_index: The chunk_index of the matched chunk (may be None).
        window_size: Number of chunks to fetch on each side (default 1).

    Returns:
        List of dicts with keys: chunk_index, content. Sorted by chunk_index.
        Returns an empty list if the document cannot be identified, chunk_index
        is unknown, or the Qdrant query fails.
    """
    if not collection or chunk_index is None:
        return []

    # Identify the parent document. Prefer file_id, fall back to source_id.
    file_id = metadata.get("file_id")
    source_id = metadata.get("source_id")

    doc_filter_condition = None
    if file_id:
        doc_filter_condition = FieldCondition(
            key="metadata.file_id",
            match=MatchValue(value=str(file_id)),
        )
    elif source_id:
        doc_filter_condition = FieldCondition(
            key="source_id",
            match=MatchValue(value=str(source_id)),
        )
    else:
        logger.debug(
            "fetch_chunk_neighbors: no document identifier in metadata",
            collection=collection,
            chunk_index=chunk_index,
        )
        return []

    lo = max(chunk_index - window_size, 0)
    hi = chunk_index + window_size

    range_condition = FieldCondition(
        key="chunk_index",
        range=Range(gte=lo, lte=hi),
    )

    scroll_filter = Filter(must=[doc_filter_condition, range_condition])

    try:
        points, _ = client.scroll(
            collection_name=collection,
            scroll_filter=scroll_filter,
            limit=window_size * 2 + 1,
            with_payload=True,
        )
    except Exception as e:
        logger.warning(
            "fetch_chunk_neighbors: scroll failed",
            collection=collection,
            chunk_index=chunk_index,
            error=str(e),
        )
        return []

    results = []
    for point in points:
        results.append({
            "chunk_index": point.payload.get("chunk_index"),
            "content": point.payload.get("content", ""),
        })

    results.sort(key=lambda x: x["chunk_index"] if x["chunk_index"] is not None else -1)
    return results


async def list_unique_field_values(
    client: QdrantClient,
    field: str,
    collections: list[str],
) -> list[str]:
    """
    Sample Qdrant points to collect unique values for a metadata field.

    Scrolls up to _SAMPLE_LIMIT points per collection and extracts distinct
    values for the given field. Values may be a scalar string or a list of
    strings in the payload.

    Args:
        client: Qdrant client instance.
        field: User-facing field name (e.g. "platforms", "doc_category").
               Must be a key in _FIELD_TO_PAYLOAD_PATH.
        collections: List of Qdrant collection names to sample from.

    Returns:
        Sorted list of unique string values found across all collections.

    Raises:
        ValueError: If the field name is not recognised.
    """
    if field not in _FIELD_TO_PAYLOAD_PATH:
        valid = sorted(_FIELD_TO_PAYLOAD_PATH.keys())
        raise ValueError(
            f"Unknown filter field '{field}'. Valid fields: {valid}"
        )

    payload_path = _FIELD_TO_PAYLOAD_PATH[field]

    # payload_path is dot-separated: "metadata.platforms" → ["metadata", "platforms"]
    path_parts = payload_path.split(".")

    unique_values: set[str] = set()

    for collection in collections:
        try:
            points, _ = client.scroll(
                collection_name=collection,
                limit=_SAMPLE_LIMIT,
                with_payload=True,
            )
        except Exception as e:
            logger.warning(
                "list_unique_field_values: scroll failed",
                collection=collection,
                field=field,
                error=str(e),
            )
            continue

        for point in points:
            payload = point.payload or {}
            # Navigate nested payload using path parts
            value = payload
            for part in path_parts:
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(part)

            if value is None:
                continue

            # Accept strings and numbers (e.g. published_year is an int); bool
            # is a subclass of int but is never a meaningful facet value, so
            # exclude it. Numbers are stringified for a uniform return type.
            def _emit(v) -> None:
                if isinstance(v, bool):
                    return
                if isinstance(v, str) and v:
                    unique_values.add(v)
                elif isinstance(v, (int, float)):
                    unique_values.add(str(v))

            if isinstance(value, list):
                for v in value:
                    _emit(v)
            else:
                _emit(value)

    return sorted(unique_values)
