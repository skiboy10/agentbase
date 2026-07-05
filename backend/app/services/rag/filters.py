"""
Metadata filter builder for Qdrant queries.

Converts structured filter dicts (from API parameters or agent config)
into Qdrant Filter objects for use in search queries.
"""
from qdrant_client import models


# Fields that can be filtered on, mapped to their Qdrant payload path
FILTERABLE_FIELDS = {
    "platforms": "metadata.platforms",
    "products": "metadata.products",
    "offerings": "metadata.offerings",
    "doc_category": "metadata.doc_category",
    "companies": "metadata.companies",
    "file_id": "metadata.file_id",
    "source_id": "source_id",
    # Publish-date facets (e.g. YouTube transcripts). published_date is an int
    # YYYYMMDD supporting range queries via {"gte": 20260101, "lte": 20261231};
    # year/month support exact or MatchAny.
    "published_date": "metadata.published_date",
    "published_year": "metadata.published_year",
    "published_month": "metadata.published_month",
}

# Fields to index as keyword in Qdrant payload schema
KEYWORD_INDEX_FIELDS = [
    ("metadata.platforms", models.PayloadSchemaType.KEYWORD),
    ("metadata.products", models.PayloadSchemaType.KEYWORD),
    ("metadata.offerings", models.PayloadSchemaType.KEYWORD),
    ("metadata.doc_category", models.PayloadSchemaType.KEYWORD),
    ("metadata.companies", models.PayloadSchemaType.KEYWORD),
    ("metadata.file_id", models.PayloadSchemaType.KEYWORD),
    ("source_id", models.PayloadSchemaType.KEYWORD),
    # Publish-date facets. INTEGER schema enables Range queries on the
    # YYYYMMDD date and on the year; month stays KEYWORD for exact/MatchAny.
    ("metadata.published_date", models.PayloadSchemaType.INTEGER),
    ("metadata.published_year", models.PayloadSchemaType.INTEGER),
    ("metadata.published_month", models.PayloadSchemaType.KEYWORD),
    # Sub-source filter overlay: list of canonical ancestor folder paths.
    # Indexed as keyword so MatchAny(path_prefix) is O(log N).
    ("folder_ancestors", models.PayloadSchemaType.KEYWORD),
    # File path of the chunk's source file. Indexed so per-file re-index
    # operations (FileItemIndexer) can count and delete prior chunks
    # accurately; without this, count(exact=False) returned approximate
    # counts via segment heuristics that overcounted by orders of magnitude.
    ("source", models.PayloadSchemaType.KEYWORD),
]


def build_metadata_filter(filters: dict) -> models.Filter | None:
    """
    Convert a structured filter dict into a Qdrant Filter.

    Args:
        filters: Dict with optional keys:
            - platforms: str | list[str]
            - products: str | list[str]
            - offerings: str | list[str]
            - doc_category: str | list[str]
            - companies: str | list[str]
            - file_id: str | list[str]
            - source_id: str | list[str]
            - path_prefix: str | list[str]   -- canonical ancestor paths;
                                                emits a MatchAny on
                                                ``folder_ancestors`` (must)
            - path_excludes: list[str]       -- canonical ancestor paths;
                                                emits a MatchAny on
                                                ``folder_ancestors`` (must_not)

    Returns:
        Qdrant Filter object with AND (must) conditions and optional must_not,
        or None if filters is empty or yields no conditions.

    Examples:
        >>> build_metadata_filter({"platforms": ["AcmeCRM"], "doc_category": "proposal"})
        # => Filter with two must conditions: MatchAny + MatchValue
    """
    if not filters:
        return None

    must_conditions: list[models.Condition] = []
    must_not_conditions: list[models.Condition] = []

    for filter_key, payload_path in FILTERABLE_FIELDS.items():
        value = filters.get(filter_key)
        if value is None:
            continue

        if isinstance(value, list):
            # Non-empty list → MatchAny (OR across values)
            non_empty = [v for v in value if v]
            if not non_empty:
                continue
            must_conditions.append(
                models.FieldCondition(
                    key=payload_path,
                    match=models.MatchAny(any=non_empty),
                )
            )
        elif isinstance(value, dict):
            # Range query → Qdrant Range, e.g. {"gte": 20260101, "lte": 20261231}.
            # Only numeric bounds are honoured; non-numeric bounds are dropped
            # here (fail-soft at build time rather than erroring inside Qdrant at
            # query time). bool is excluded (it is a subclass of int).
            bounds = {
                k: value[k]
                for k in ("gte", "lte", "gt", "lt")
                if isinstance(value.get(k), (int, float))
                and not isinstance(value.get(k), bool)
            }
            if bounds:
                must_conditions.append(
                    models.FieldCondition(
                        key=payload_path,
                        range=models.Range(**bounds),
                    )
                )
        elif isinstance(value, bool):
            # Guard before int (bool is a subclass of int) — booleans are not
            # valid filter values here, so skip them.
            continue
        elif isinstance(value, (int, float)):
            # Single number → exact MatchValue (e.g. published_year=2026)
            must_conditions.append(
                models.FieldCondition(
                    key=payload_path,
                    match=models.MatchValue(value=value),
                )
            )
        elif isinstance(value, str) and value:
            # Single string → MatchValue
            must_conditions.append(
                models.FieldCondition(
                    key=payload_path,
                    match=models.MatchValue(value=value),
                )
            )
        # Skip falsy/empty values

    # Sub-source filter overlay (path_prefix + path_excludes operate on
    # folder_ancestors). Callers are expected to pre-canonicalise these via
    # path_utils.canonicalise_path; we just consume them.
    prefix_val = filters.get("path_prefix")
    if prefix_val:
        if isinstance(prefix_val, str):
            prefixes = [prefix_val]
        else:
            prefixes = [p for p in prefix_val if p]
        if prefixes:
            must_conditions.append(
                models.FieldCondition(
                    key="folder_ancestors",
                    match=models.MatchAny(any=prefixes),
                )
            )

    excludes_val = filters.get("path_excludes")
    if excludes_val:
        excludes = [e for e in (excludes_val if isinstance(excludes_val, list) else [excludes_val]) if e]
        if excludes:
            must_not_conditions.append(
                models.FieldCondition(
                    key="folder_ancestors",
                    match=models.MatchAny(any=excludes),
                )
            )

    if not must_conditions and not must_not_conditions:
        return None

    return models.Filter(
        must=must_conditions or None,
        must_not=must_not_conditions or None,
    )


def merge_filters(
    base_filter: models.Filter | None,
    extra_filter: models.Filter | None,
) -> models.Filter | None:
    """
    Merge two Qdrant filters using AND semantics.

    Concatenates both ``must`` and ``must_not`` lists. Returns None if both
    inputs are None.
    """
    if base_filter is None and extra_filter is None:
        return None
    if base_filter is None:
        return extra_filter
    if extra_filter is None:
        return base_filter

    base_must = list(base_filter.must or [])
    extra_must = list(extra_filter.must or [])
    base_must_not = list(base_filter.must_not or [])
    extra_must_not = list(extra_filter.must_not or [])

    merged_must = base_must + extra_must
    merged_must_not = base_must_not + extra_must_not

    return models.Filter(
        must=merged_must or None,
        must_not=merged_must_not or None,
    )
