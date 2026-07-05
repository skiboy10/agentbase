"""
Search implementations for RAG service.

Provides four search strategies:
- search_standard: dense vector search, single embedding model
- search_multi_embedding: vector search across sources with different embedding models
- search_hybrid: dense + keyword search fused via RRF (uses native Qdrant fusion when available)
- search_grouped: vector search with results grouped by source document (max N chunks per doc)
"""
from typing import Optional
from collections import defaultdict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchText, MatchAny
import structlog

from app.models import Source, ProjectSource
from .types import SearchResult
from .fusion import reciprocal_rank_fusion, weighted_rrf
from .embedding import get_embedding_config, embed_query, embed_query_with_model
from .source_resolver import resolve_source_ids, overlay_filters_for_root

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Native Qdrant fusion capability detection
#
# qdrant-client >= 1.9.0 exposes models.Prefetch and models.FusionQuery which
# let the server do the RRF merge, saving a round-trip and improving accuracy.
# ---------------------------------------------------------------------------
_SUPPORTS_NATIVE_FUSION = False
_SUPPORTS_QUERY_GROUPS = False

try:
    from qdrant_client import models as _qdm
    # Prefetch and FusionQuery classes exist in qdrant-client 1.9.x but
    # query_filter on Prefetch is not supported in all versions.
    # Disabled until verified with the deployed Qdrant server version.
    # if hasattr(_qdm, "Prefetch") and hasattr(_qdm, "FusionQuery"):
    #     _SUPPORTS_NATIVE_FUSION = True
    pass
    # query_groups was added in qdrant-client 1.7.x
    if hasattr(QdrantClient, "query_groups"):
        _SUPPORTS_QUERY_GROUPS = True
except Exception:
    pass

logger.debug(
    "Qdrant client capabilities detected at module load",
    native_fusion_available=_SUPPORTS_NATIVE_FUSION,
    native_fusion=_SUPPORTS_NATIVE_FUSION,
    query_groups=_SUPPORTS_QUERY_GROUPS,
)


async def search_multi_embedding(
    db: AsyncSession,
    client: QdrantClient,
    query: str,
    source_ids: list[str],
    top_k: int = 5,
    score_threshold: float = 0.0
) -> list[SearchResult]:
    """
    Search across sources with potentially different embedding models.

    This method handles the case where knowledge sources were indexed with
    different embedding models. It groups sources by their embedding config,
    queries each group with the appropriate model, and merges results using
    Reciprocal Rank Fusion (RRF).

    Args:
        db: Database session
        client: Qdrant client
        query: The search query
        source_ids: List of source IDs to search across
        top_k: Number of results to return
        score_threshold: Minimum score threshold for results

    Returns:
        List of SearchResult objects merged and ranked by RRF score
    """
    if not source_ids:
        return []

    # Sub-source ids → parent root id + overlay
    source_ids, sub_source_overlay = await resolve_source_ids(db, source_ids)

    # When sources are explicitly requested by ID, include any source that has
    # actual chunks in Qdrant (collection_name set), regardless of its current
    # `status`. A source can be in status=error from a downstream failure
    # (e.g. enrichment, library binding) even after its chunks were successfully
    # indexed — those chunks should still be searchable. (#106)
    stmt = select(Source).where(
        Source.id.in_(source_ids),
        Source.collection_name.isnot(None),
    )
    result = await db.execute(stmt)
    sources = list(result.scalars().all())

    if not sources:
        logger.info("No searchable sources found for multi-embedding search (no collection_name)")
        return []

    # Get default embedding config for sources without explicit config
    default_provider, default_model, _ = await get_embedding_config(db)

    # Group sources by (embedding_provider, embedding_model)
    embedding_groups: dict[tuple[str, str], list[Source]] = defaultdict(list)

    for source in sources:
        if not source.collection_name:
            continue

        # Use source's embedding config, or fall back to default
        provider = source.embedding_provider or default_provider
        model = source.embedding_model or default_model

        embedding_groups[(provider, model)].append(source)

    if not embedding_groups:
        logger.info("No sources with collections found for search")
        return []

    logger.info(
        "Searching across embedding groups",
        groups=[
            {"provider": p, "model": m, "source_count": len(sources)}
            for (p, m), sources in embedding_groups.items()
        ]
    )

    # Collect ranked results from each embedding group
    all_result_lists: list[list[SearchResult]] = []

    for (provider, model), group_sources in embedding_groups.items():
        try:
            # Generate query embedding using this group's model
            query_embedding = await embed_query_with_model(query, provider, model)

            # Get source IDs for this group
            group_source_ids = [s.id for s in group_sources]

            # Search each collection in this group
            group_results: list[SearchResult] = []

            for source in group_sources:
                try:
                    # Build per-source filter: source_id constraint + sub-source overlay.
                    must_conds = [
                        FieldCondition(
                            key="source_id",
                            match=MatchAny(any=group_source_ids),
                        )
                    ]
                    must_not_conds = []
                    root_overlay = sub_source_overlay.get(source.id) or {}
                    prefixes = root_overlay.get("path_prefix") or []
                    excludes = root_overlay.get("path_excludes") or []
                    if prefixes:
                        must_conds.append(
                            FieldCondition(
                                key="folder_ancestors",
                                match=MatchAny(any=prefixes),
                            )
                        )
                    if excludes:
                        must_not_conds.append(
                            FieldCondition(
                                key="folder_ancestors",
                                match=MatchAny(any=excludes),
                            )
                        )

                    search_response = client.query_points(
                        collection_name=source.collection_name,
                        query=query_embedding,
                        query_filter=Filter(
                            must=must_conds,
                            must_not=must_not_conds or None,
                        ),
                        limit=top_k * 2,  # Fetch more to account for filtering
                        with_payload=True,
                        score_threshold=score_threshold if score_threshold > 0 else None,
                    )

                    for hit in search_response.points:
                        group_results.append(SearchResult(
                            content=hit.payload.get("content", ""),
                            source=hit.payload.get("source", ""),
                            score=hit.score,
                            title=hit.payload.get("title", ""),
                            source_name=source.name,
                            document_path=hit.payload.get("source", ""),
                            collection=source.collection_name,
                            metadata={
                                "source_id": hit.payload.get("source_id"),
                                "document_id": hit.payload.get("document_id"),
                                "chunk_index": hit.payload.get("chunk_index"),
                                "collection": source.collection_name,
                                "source_name": source.name,
                                "title": hit.payload.get("title", ""),
                                "content_hash": hit.payload.get("content_hash"),
                                "scraped_at": hit.payload.get("scraped_at"),
                                "embedding_model": hit.payload.get("embedding_model"),
                                "embedding_provider": provider,
                            }
                        ))
                except Exception as e:
                    logger.warning(
                        "Search failed for collection in multi-embedding search",
                        collection=source.collection_name,
                        provider=provider,
                        model=model,
                        error=str(e),
                    )

            # Sort by score within this group (highest first)
            group_results.sort(key=lambda x: x.score, reverse=True)

            if group_results:
                all_result_lists.append(group_results)

        except Exception as e:
            logger.error(
                "Failed to process embedding group",
                provider=provider,
                model=model,
                error=str(e),
            )

    if not all_result_lists:
        return []

    # If only one group, no need for fusion
    if len(all_result_lists) == 1:
        return all_result_lists[0][:top_k]

    # Merge results using Reciprocal Rank Fusion
    merged = reciprocal_rank_fusion(all_result_lists)

    return merged[:top_k]


async def search_standard(
    db: AsyncSession,
    client: QdrantClient,
    query: str,
    project_id: Optional[str] = None,
    top_k: int = 5,
    strict_embedding_match: bool = True,
    source_ids: Optional[list[str]] = None,
    filters: Optional[dict] = None,
) -> list[SearchResult]:
    """
    Search the knowledge base for relevant documents.

    Args:
        db: Database session
        client: Qdrant client
        query: The search query
        project_id: Optional project to scope search to
        top_k: Number of results to return
        strict_embedding_match: If True, skip sources with different embedding models
        source_ids: Optional list of specific knowledge source IDs to search

    Returns:
        List of SearchResult objects ranked by relevance
    """
    # Get current embedding config
    current_provider, current_model, _ = await get_embedding_config(db)
    current_embedding_id = f"{current_provider}/{current_model}"

    # Sub-source ids in source_ids resolve to their parent root + an overlay
    # that adds path_prefix / path_excludes filters at query time.
    sub_source_overlay: dict[str, dict] = {}
    if source_ids:
        source_ids, sub_source_overlay = await resolve_source_ids(db, source_ids)

    # Get indexed sources - by specific IDs or project
    if source_ids:
        # Explicit source selection: accept sources with chunks in Qdrant
        # regardless of overall status (#106 — status=error can occur after
        # successful indexing due to downstream binding/enrichment failures).
        stmt = select(Source).where(
            Source.id.in_(source_ids),
            Source.collection_name.isnot(None),
        )
        result = await db.execute(stmt)
        sources = list(result.scalars().all())
    elif project_id:
        # 1. Get project-specific sources (sources created for this project)
        project_sources_stmt = select(Source).where(
            Source.project_id == project_id,
            Source.status == "indexed"
        )
        project_result = await db.execute(project_sources_stmt)
        project_sources = list(project_result.scalars().all())

        # 2. Get assigned global sources via junction table
        assigned_global_stmt = (
            select(Source)
            .join(ProjectSource, Source.id == ProjectSource.source_id)
            .where(
                ProjectSource.project_id == project_id,
                Source.project_id.is_(None),
                Source.status == "indexed"
            )
        )
        assigned_result = await db.execute(assigned_global_stmt)
        assigned_sources = list(assigned_result.scalars().all())

        # Combine both (no duplicates since project-specific can't be global)
        sources = project_sources + assigned_sources
    else:
        # No project context - return all indexed sources (roots only — a
        # sub-source has no own collection, so excluding it here keeps the
        # query loop from touching sources with collection_name IS NULL).
        stmt = select(Source).where(
            Source.status == "indexed",
            Source.parent_source_id.is_(None),
        )
        result = await db.execute(stmt)
        sources = list(result.scalars().all())

    if not sources:
        logger.info("No indexed sources found for search")
        return []

    # Filter sources by embedding model compatibility
    compatible_sources = []
    skipped_sources = []

    for source in sources:
        if not source.collection_name:
            continue

        # Check embedding model compatibility
        source_embedding_id = None
        if source.embedding_provider and source.embedding_model:
            source_embedding_id = f"{source.embedding_provider}/{source.embedding_model}"

        if strict_embedding_match and source_embedding_id and source_embedding_id != current_embedding_id:
            skipped_sources.append({
                "name": source.name,
                "embedding": source_embedding_id,
            })
            continue

        compatible_sources.append(source)

    if skipped_sources:
        logger.warning(
            "Skipped sources due to embedding model mismatch",
            current_embedding=current_embedding_id,
            skipped=skipped_sources,
        )

    if not compatible_sources:
        logger.info("No compatible indexed sources found for search")
        return []

    # Generate query embedding
    try:
        query_embedding = await embed_query(db, query)
    except Exception as e:
        logger.error("Failed to generate query embedding", error=str(e))
        return []

    # Search each collection and aggregate results
    all_results = []

    from .filters import build_metadata_filter

    for source in compatible_sources:
        try:
            # Per-source filter overlay: callers' base filters + any sub-source
            # path_prefix / path_excludes contributed for this root.
            source_filters = overlay_filters_for_root(
                sub_source_overlay, source.id, filters
            )
            qdrant_filter = build_metadata_filter(source_filters) if source_filters else None

            query_kwargs = dict(
                collection_name=source.collection_name,
                query=query_embedding,
                limit=top_k,
                with_payload=True,
            )
            if qdrant_filter:
                query_kwargs["query_filter"] = qdrant_filter
            search_response = client.query_points(**query_kwargs)

            for hit in search_response.points:
                all_results.append(SearchResult(
                    content=hit.payload.get("content", ""),
                    source=hit.payload.get("source", ""),
                    score=hit.score,
                    title=hit.payload.get("title", ""),
                    source_name=source.name,
                    document_path=hit.payload.get("source", ""),
                    collection=source.collection_name,
                    metadata={
                        "source_id": hit.payload.get("source_id"),
                        "document_id": hit.payload.get("document_id"),
                        "chunk_index": hit.payload.get("chunk_index"),
                        "collection": source.collection_name,
                        "source_name": source.name,
                        "title": hit.payload.get("title", ""),
                        "content_hash": hit.payload.get("content_hash"),
                        "scraped_at": hit.payload.get("scraped_at"),
                        "embedding_model": hit.payload.get("embedding_model"),
                        "classification": hit.payload.get("metadata") or {},
                    }
                ))
        except Exception as e:
            logger.warning(
                "Search failed for collection",
                collection=source.collection_name,
                error=str(e),
            )

    # Sort by score and return top_k
    all_results.sort(key=lambda x: x.score, reverse=True)
    return all_results[:top_k]


async def search_hybrid(
    db: AsyncSession,
    client: QdrantClient,
    query: str,
    project_id: Optional[str] = None,
    top_k: int = 5,
    vector_weight: float = 0.7,
    filters: Optional[dict] = None,
    source_ids: Optional[list[str]] = None,
) -> list[SearchResult]:
    """
    Hybrid search combining vector similarity and text matching.

    Uses Reciprocal Rank Fusion (RRF) to combine results from:
    - Semantic search (dense vector similarity)
    - Text search (keyword matching via Qdrant text index)

    Args:
        db: Database session
        client: Qdrant client
        query: The search query
        project_id: Optional project to scope search to
        top_k: Number of results to return
        vector_weight: Weight for vector search (0-1), text weight = 1 - vector_weight

    Returns:
        List of SearchResult objects ranked by combined RRF score
    """
    # Resolve sub-sources → root + overlay before fetching Source rows.
    sub_source_overlay: dict[str, dict] = {}
    if source_ids:
        source_ids, sub_source_overlay = await resolve_source_ids(db, source_ids)

    # Get indexed sources - by specific IDs, project, or all
    if source_ids:
        # Explicit source selection: accept sources with chunks in Qdrant
        # regardless of overall status (#106).
        stmt = select(Source).where(
            Source.id.in_(source_ids),
            Source.collection_name.isnot(None),
        )
        result = await db.execute(stmt)
        sources = list(result.scalars().all())
    elif project_id:
        project_sources_stmt = select(Source).where(
            Source.project_id == project_id,
            Source.status == "indexed"
        )
        project_result = await db.execute(project_sources_stmt)
        project_sources = list(project_result.scalars().all())

        assigned_global_stmt = (
            select(Source)
            .join(ProjectSource, Source.id == ProjectSource.source_id)
            .where(
                ProjectSource.project_id == project_id,
                Source.project_id.is_(None),
                Source.status == "indexed"
            )
        )
        assigned_result = await db.execute(assigned_global_stmt)
        assigned_sources = list(assigned_result.scalars().all())
        sources = project_sources + assigned_sources
    else:
        # Roots only — sub-sources don't carry chunks of their own.
        stmt = select(Source).where(
            Source.status == "indexed",
            Source.parent_source_id.is_(None),
        )
        result = await db.execute(stmt)
        sources = list(result.scalars().all())

    if not sources:
        return []

    # Get current embedding config for compatibility check
    current_provider, current_model, _ = await get_embedding_config(db)
    current_embedding_id = f"{current_provider}/{current_model}"

    # Filter to compatible sources (has collection and matching embedding model)
    compatible_sources = []
    skipped_sources = []

    for s in sources:
        if not s.collection_name:
            continue

        source_embedding_id = None
        if s.embedding_provider and s.embedding_model:
            source_embedding_id = f"{s.embedding_provider}/{s.embedding_model}"

        if source_embedding_id and source_embedding_id != current_embedding_id:
            skipped_sources.append({"name": s.name, "embedding": source_embedding_id})
            continue

        compatible_sources.append(s)

    if skipped_sources:
        logger.warning(
            "Hybrid search: skipped sources due to embedding model mismatch",
            current_embedding=current_embedding_id,
            skipped=skipped_sources,
        )

    if not compatible_sources:
        return []

    # Generate query embedding for vector search
    try:
        query_embedding = await embed_query(db, query)
    except Exception as e:
        logger.error("Failed to generate query embedding", error=str(e))
        return []

    # Use native Qdrant server-side fusion when available (qdrant-client >= 1.9.0).
    # Server-side RRF is more accurate because it can see the full ranking across
    # all points, not just the top-N returned to the client.
    #
    # Upgrade path: update requirements.txt to qdrant-client>=1.9.0 to enable.
    if _SUPPORTS_NATIVE_FUSION:
        return await _search_hybrid_native(
            client, compatible_sources, query_embedding, query, top_k
        )

    # Fallback: Python-side weighted RRF (works with qdrant-client >= 1.7.0)
    from .filters import build_metadata_filter

    # Accumulate raw results from every collection BEFORE assigning rank.
    # Previously rank was per-collection (0,1,2,... within each source), which
    # meant every collection's top hit shared rank 0 — after RRF + max-norm
    # all top results normalized to score=1.0 (#106 bug c). We now sort
    # globally by raw vector score across collections and assign a single
    # cross-collection rank before fusion. The cross-collection ID combines
    # (collection_name, hit.id) since Qdrant point IDs are scoped per
    # collection and can otherwise collide.
    vector_raw: list[tuple[str, SearchResult, float]] = []  # (doc_id, result, raw_score)
    text_raw: list[tuple[str, SearchResult]] = []           # (doc_id, result) in scan order

    for source in compatible_sources:
        try:
            # Per-source overlay (sub-source path filters + caller's filters)
            source_filters = overlay_filters_for_root(
                sub_source_overlay, source.id, filters
            )
            qdrant_filter = build_metadata_filter(source_filters) if source_filters else None

            # 1. Vector search
            query_kwargs = dict(
                collection_name=source.collection_name,
                query=query_embedding,
                limit=top_k * 2,
                with_payload=True,
            )
            if qdrant_filter:
                query_kwargs["query_filter"] = qdrant_filter
            vector_response = client.query_points(**query_kwargs)

            for hit in vector_response.points:
                result = SearchResult(
                    content=hit.payload.get("content", ""),
                    source=hit.payload.get("source", ""),
                    score=hit.score,
                    title=hit.payload.get("title", ""),
                    source_name=source.name,
                    document_path=hit.payload.get("source", ""),
                    collection=source.collection_name,
                    metadata={
                        "source_id": hit.payload.get("source_id"),
                        "document_id": hit.payload.get("document_id"),
                        "chunk_index": hit.payload.get("chunk_index"),
                        "collection": source.collection_name,
                        "source_name": source.name,
                        "title": hit.payload.get("title", ""),
                        "content_hash": hit.payload.get("content_hash"),
                        "scraped_at": hit.payload.get("scraped_at"),
                        "embedding_model": hit.payload.get("embedding_model"),
                        "fusion_method": "python_rrf",
                        "vector_score": hit.score,
                        "classification": hit.payload.get("metadata") or {},
                    }
                )
                doc_id = f"{source.collection_name}:{hit.id}"
                vector_raw.append((doc_id, result, hit.score))

            # 2. Text search (keyword matching)
            try:
                text_filter_must = [
                    FieldCondition(
                        key="content",
                        match=MatchText(text=query)
                    )
                ]
                if qdrant_filter and qdrant_filter.must:
                    text_filter_must.extend(qdrant_filter.must)
                text_response = client.scroll(
                    collection_name=source.collection_name,
                    scroll_filter=Filter(must=text_filter_must),
                    limit=top_k * 2,
                    with_payload=True,
                )

                for point in text_response[0]:
                    result = SearchResult(
                        content=point.payload.get("content", ""),
                        source=point.payload.get("source", ""),
                        score=1.0,  # Text match has no native score; placeholder
                        title=point.payload.get("title", ""),
                        source_name=source.name,
                        document_path=point.payload.get("source", ""),
                        collection=source.collection_name,
                        metadata={
                            "source_id": point.payload.get("source_id"),
                            "document_id": point.payload.get("document_id"),
                            "chunk_index": point.payload.get("chunk_index"),
                            "collection": source.collection_name,
                            "source_name": source.name,
                            "title": point.payload.get("title", ""),
                            "content_hash": point.payload.get("content_hash"),
                            "scraped_at": point.payload.get("scraped_at"),
                            "embedding_model": point.payload.get("embedding_model"),
                            "fusion_method": "python_rrf",
                            "classification": point.payload.get("metadata") or {},
                        }
                    )
                    doc_id = f"{source.collection_name}:{point.id}"
                    text_raw.append((doc_id, result))
            except Exception as e:
                # Text index may not exist on older collections
                logger.debug(
                    "Text search failed for collection (may not have text index)",
                    collection=source.collection_name,
                    error=str(e),
                )

        except Exception as e:
            logger.warning(
                "Hybrid search failed for collection",
                collection=source.collection_name,
                error=str(e),
            )

    # Assign cross-collection ranks AFTER all collections have been queried.
    # Vector results: rank by descending raw vector score (deduping by doc_id —
    # keep first/best occurrence).
    vector_raw.sort(key=lambda t: t[2], reverse=True)
    vector_results: dict = {}
    for doc_id, result, _score in vector_raw:
        if doc_id not in vector_results:
            vector_results[doc_id] = (result, len(vector_results))

    # Text results: Qdrant scroll doesn't return scores — preserve scan order
    # but dedupe across collections.
    text_results: dict = {}
    for doc_id, result in text_raw:
        if doc_id not in text_results:
            text_results[doc_id] = (result, len(text_results))

    # Apply weighted Reciprocal Rank Fusion
    fused = weighted_rrf(vector_results, text_results, vector_weight)

    return fused[:top_k]


async def _search_hybrid_native(
    client: QdrantClient,
    sources: list,
    query_embedding: list[float],
    query_text: str,
    top_k: int,
) -> list[SearchResult]:
    """
    Hybrid search using Qdrant's native server-side RRF fusion (qdrant-client >= 1.9.0).

    Uses two Prefetch branches fused server-side by Qdrant RRF:
      1. Dense vector retrieval (broad semantic candidates, no filter)
      2. Text-filtered dense retrieval (keyword-restricted candidates)

    The RRF merger promotes points that appear in BOTH branches — i.e., documents
    that are both semantically similar AND contain the query terms. This is a
    practical approximation of hybrid search without requiring a sparse vector index.

    Limitation: True sparse-vector hybrid (BM25 + dense) requires configuring a
    named sparse vector during indexing. This approach achieves a similar benefit
    using the existing text payload index on 'content'. If the text index is absent
    the second Prefetch returns empty results and only the dense branch contributes.

    Args:
        client: Qdrant client (qdrant-client >= 1.9.0)
        sources: Source ORM objects with collection_name
        query_embedding: Dense query vector
        query_text: Raw query string (used as MatchText keyword filter)
        top_k: Number of results to return per collection
    """
    from qdrant_client import models as qdm  # Guarded: only called when native fusion confirmed

    all_results: list[SearchResult] = []

    # Build the text filter — requires a FullText index on 'content' in the collection.
    # If the index is missing, the second prefetch silently returns 0 results.
    text_filter = qdm.Filter(
        must=[
            qdm.FieldCondition(
                key="content",
                match=qdm.MatchText(text=query_text),
            )
        ]
    )

    for source in sources:
        try:
            response = client.query_points(
                collection_name=source.collection_name,
                prefetch=[
                    # Branch 1: broad dense vector retrieval (semantic similarity)
                    qdm.Prefetch(
                        query=query_embedding,
                        limit=top_k * 3,
                    ),
                    # Branch 2: dense retrieval restricted to keyword-matching chunks
                    # Scores documents that match the query text AND are semantically
                    # close — RRF promotes items appearing in both result sets.
                    qdm.Prefetch(
                        query=query_embedding,
                        query_filter=text_filter,
                        limit=top_k * 3,
                    ),
                ],
                query=qdm.FusionQuery(fusion=qdm.Fusion.RRF),
                limit=top_k,
                with_payload=True,
            )

            for hit in response.points:
                all_results.append(SearchResult(
                    content=hit.payload.get("content", ""),
                    source=hit.payload.get("source", ""),
                    score=hit.score,
                    title=hit.payload.get("title", ""),
                    source_name=source.name,
                    document_path=hit.payload.get("source", ""),
                    collection=source.collection_name,
                    metadata={
                        "source_id": hit.payload.get("source_id"),
                        "document_id": hit.payload.get("document_id"),
                        "chunk_index": hit.payload.get("chunk_index"),
                        "collection": source.collection_name,
                        "source_name": source.name,
                        "title": hit.payload.get("title", ""),
                        "content_hash": hit.payload.get("content_hash"),
                        "scraped_at": hit.payload.get("scraped_at"),
                        "embedding_model": hit.payload.get("embedding_model"),
                        "fusion_method": "native_rrf",
                    }
                ))

        except Exception as e:
            logger.warning(
                "Native hybrid search failed for collection — falling back to vector-only for this source",
                collection=source.collection_name,
                error=str(e),
            )
            # Individual source failure: skip, continue with other collections

    all_results.sort(key=lambda r: r.score, reverse=True)
    return all_results[:top_k]


async def search_grouped(
    db: AsyncSession,
    client: QdrantClient,
    query: str,
    project_id: Optional[str] = None,
    top_k: int = 5,
    source_ids: Optional[list[str]] = None,
    filters=None,
    group_size: int = 2,
) -> list[SearchResult]:
    """
    Search with results grouped by source document.

    Uses Qdrant's query_groups API to return at most group_size chunks per
    unique document (identified by metadata.file_id). This prevents a single
    large document from monopolising the result set.

    Falls back to search_standard if:
    - query_groups is not supported by this client version
    - The collection has no file_id metadata (graceful degradation)

    Args:
        db: Database session
        client: Qdrant client
        query: The search query
        project_id: Optional project to scope the search to
        top_k: Number of document groups to return (not total chunks)
        source_ids: Optional list of specific knowledge source IDs to search
        filters: Optional Qdrant Filter to apply (from filters.py)
        group_size: Maximum chunks to return per document group (default 2)

    Returns:
        List of SearchResult objects, at most group_size per unique file_id.
        If query_groups is unavailable, returns results from search_standard.
    """
    if not _SUPPORTS_QUERY_GROUPS:
        logger.info(
            "query_groups not supported by this qdrant-client version — "
            "falling back to search_standard. Upgrade to qdrant-client>=1.7.0 "
            "to enable grouped search.",
            qdrant_client_version=_qdrant_version,
        )
        return await search_standard(
            db, client, query, project_id, top_k,
            strict_embedding_match=True, source_ids=source_ids
        )

    # Resolve sub-sources → root + overlay
    sub_source_overlay: dict[str, dict] = {}
    if source_ids:
        source_ids, sub_source_overlay = await resolve_source_ids(db, source_ids)

    # Resolve sources (same logic as search_standard)
    if source_ids:
        # Explicit source selection: accept sources with chunks in Qdrant
        # regardless of overall status (#106).
        stmt = select(Source).where(
            Source.id.in_(source_ids),
            Source.collection_name.isnot(None),
        )
        result = await db.execute(stmt)
        sources = list(result.scalars().all())
    elif project_id:
        project_sources_stmt = select(Source).where(
            Source.project_id == project_id,
            Source.status == "indexed"
        )
        project_result = await db.execute(project_sources_stmt)
        project_sources = list(project_result.scalars().all())

        assigned_global_stmt = (
            select(Source)
            .join(ProjectSource, Source.id == ProjectSource.source_id)
            .where(
                ProjectSource.project_id == project_id,
                Source.project_id.is_(None),
                Source.status == "indexed"
            )
        )
        assigned_result = await db.execute(assigned_global_stmt)
        assigned_sources = list(assigned_result.scalars().all())
        sources = project_sources + assigned_sources
    else:
        # Roots only — sub-sources don't own chunks.
        stmt = select(Source).where(
            Source.status == "indexed",
            Source.parent_source_id.is_(None),
        )
        result = await db.execute(stmt)
        sources = list(result.scalars().all())

    if not sources:
        logger.info("No indexed sources found for grouped search")
        return []

    compatible_sources = [s for s in sources if s.collection_name]
    if not compatible_sources:
        return []

    # Generate query embedding
    try:
        query_embedding = await embed_query(db, query)
    except Exception as e:
        logger.error("Failed to generate query embedding for grouped search", error=str(e))
        return []

    all_results: list[SearchResult] = []

    from .filters import build_metadata_filter, merge_filters
    from qdrant_client import models as _qdm_mod

    # Normalise the inbound `filters` arg: callers pass either a dict
    # (preferred) or a pre-built Qdrant Filter object. Convert the dict form
    # to a Filter so we can merge_filter() it with the per-source overlay.
    if isinstance(filters, dict):
        base_filter_obj = build_metadata_filter(filters)
    else:
        base_filter_obj = filters  # already a Filter or None

    for source in compatible_sources:
        try:
            # Merge per-source sub-source overlay onto the base filter.
            overlay_filters = overlay_filters_for_root(
                sub_source_overlay, source.id, None
            )
            overlay_filter_obj = (
                build_metadata_filter(overlay_filters) if overlay_filters else None
            )
            source_filter = merge_filters(base_filter_obj, overlay_filter_obj)

            groups_response = client.query_groups(
                collection_name=source.collection_name,
                query=query_embedding,
                group_by="metadata.file_id",
                limit=top_k,
                group_size=group_size,
                query_filter=source_filter,
                with_payload=True,
            )

            for group in groups_response.groups:
                for hit in group.hits:
                    all_results.append(SearchResult(
                        content=hit.payload.get("content", ""),
                        source=hit.payload.get("source", ""),
                        score=hit.score,
                        title=hit.payload.get("title", ""),
                        source_name=source.name,
                        document_path=hit.payload.get("source", ""),
                        collection=source.collection_name,
                        metadata={
                            "source_id": hit.payload.get("source_id"),
                            "document_id": hit.payload.get("document_id"),
                            "chunk_index": hit.payload.get("chunk_index"),
                            "collection": source.collection_name,
                            "source_name": source.name,
                            "title": hit.payload.get("title", ""),
                            "content_hash": hit.payload.get("content_hash"),
                            "scraped_at": hit.payload.get("scraped_at"),
                            "embedding_model": hit.payload.get("embedding_model"),
                            "file_id": hit.payload.get("metadata", {}).get("file_id"),
                            "group_id": str(group.id),
                            "search_mode": "grouped",
                        }
                    ))

        except Exception as e:
            err_str = str(e).lower()
            if "file_id" in err_str or "not found" in err_str or "unknown field" in err_str:
                # Collection doesn't have file_id in metadata — fall back to standard search
                logger.info(
                    "Collection lacks file_id metadata — falling back to standard search for this source",
                    collection=source.collection_name,
                )
                fallback = await search_standard(
                    db, client, query, project_id=None, top_k=top_k,
                    strict_embedding_match=True, source_ids=[source.id]
                )
                all_results.extend(fallback)
            else:
                logger.warning(
                    "Grouped search failed for collection",
                    collection=source.collection_name,
                    error=str(e),
                )

    all_results.sort(key=lambda r: r.score, reverse=True)
    return all_results[:top_k]
