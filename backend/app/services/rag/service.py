"""
RAG Service - Main service class orchestrating RAG operations.

This service provides the core RAG functionality:
- Query embedding generation
- Semantic search over knowledge base
- Hybrid search (vector + text, RRF fusion)
- Grouped search (max N chunks per source document)
- Deep search (query decomposition + parallel sub-query search + fusion)
- Optional reranking via cross-encoder (Ollama reranker models)
- Context formatting for LLM consumption
"""
import asyncio
import time
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.providers.embedding_registry import get_embedding_registry
from app.models import Library

logger = structlog.get_logger()
from .types import SearchResult, SubQuery, DeepSearchResult, RAGContext
from .client import get_qdrant_client
from .embedding import get_embedding_config, embed_query, embed_query_with_model
from .search import search_standard, search_multi_embedding, search_hybrid, search_grouped
from .context import get_context_for_query
from .reranker import RerankerService
from .decomposer import QueryDecomposer
from .fusion import reciprocal_rank_fusion


def _results_to_reranker_docs(results: list[SearchResult]) -> list[dict]:
    """
    Convert SearchResult list to flat dicts for the reranker service.

    Preserves the original SearchResult's top-level citation fields (title,
    source_name, document_path, collection) inside the dict under a _sr_ prefix
    so they survive the reranker round-trip without colliding with payload keys.
    Does not mutate the original SearchResult objects.
    """
    return [
        {
            "content": r.content,
            "source": r.source,
            "score": r.score,
            # Stash top-level citation fields so they survive the round-trip
            "_sr_title": r.title,
            "_sr_source_name": r.source_name,
            "_sr_document_path": r.document_path,
            "_sr_collection": r.collection,
            **r.metadata,
        }
        for r in results
    ]


def _reranker_docs_to_results(docs: list[dict]) -> list[SearchResult]:
    """
    Convert reranker output dicts back to SearchResult objects.

    Works on a copy of each dict to avoid mutating the reranker's output.
    The reranker adds '_rerank_score'; we store it as both the primary ``score``
    AND the dedicated ``rerank_score`` field so callers can inspect both values.
    The original retrieval ``score`` moves to ``metadata["original_score"]``.
    """
    results = []
    for raw_doc in docs:
        doc = dict(raw_doc)  # work on a copy — do not mutate the input
        content = doc.pop("content", "")
        source = doc.pop("source", "")
        rerank_score = doc.pop("_rerank_score", None)
        original_score = doc.pop("score", 0.0)
        # Recover top-level citation fields stashed by _results_to_reranker_docs
        title = doc.pop("_sr_title", "")
        source_name = doc.pop("_sr_source_name", "")
        document_path = doc.pop("_sr_document_path", "")
        collection = doc.pop("_sr_collection", "")

        # Use rerank score as the primary score; preserve original for debugging
        score = rerank_score if rerank_score is not None else original_score
        if rerank_score is not None:
            doc["original_score"] = original_score

        results.append(SearchResult(
            content=content,
            source=source,
            score=score,
            title=title,
            source_name=source_name,
            document_path=document_path,
            collection=collection,
            rerank_score=rerank_score,
            metadata=doc,
        ))
    return results


class RAGService:
    """
    Service for Retrieval-Augmented Generation operations.

    Handles:
    - Embedding queries
    - Searching the vector store (standard, hybrid, grouped)
    - Optional cross-encoder reranking
    - Formatting context for LLM consumption
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = get_qdrant_client()
        self.embedding_registry = get_embedding_registry()
        self._reranker: Optional[RerankerService] = None
        self._decomposer: Optional[QueryDecomposer] = None

    def _get_reranker(self) -> RerankerService:
        """Lazy init of reranker service."""
        if self._reranker is None:
            self._reranker = RerankerService()
        return self._reranker

    def _get_decomposer(self) -> QueryDecomposer:
        """Lazy init of query decomposer — caches health check across calls."""
        if self._decomposer is None:
            self._decomposer = QueryDecomposer()
        return self._decomposer

    async def _resolve_kb_source_ids(self, knowledge_base_id: str) -> list[str]:
        """Resolve a Library ID to its constituent source IDs.

        Raises ValueError if the KB doesn't exist or has no sources.
        """
        from sqlalchemy.orm import selectinload

        stmt = (
            select(Library)
            .options(selectinload(Library.sources))
            .where(Library.id == knowledge_base_id)
        )
        result = await self.db.execute(stmt)
        kb = result.scalar_one_or_none()

        if kb is None:
            raise ValueError(f"Library '{knowledge_base_id}' not found")

        source_ids = [s.id for s in kb.sources]
        if not source_ids:
            raise ValueError(f"Library '{kb.name}' has no sources")

        logger.info(
            "Resolved KB to sources",
            kb_id=knowledge_base_id,
            kb_name=kb.name,
            source_count=len(source_ids),
        )
        return source_ids

    async def get_embedding_config(self) -> tuple[str, str, int]:
        """Get the configured embedding provider, model, and vector size."""
        return await get_embedding_config(self.db)

    async def embed_query(self, query: str) -> list[float]:
        """Generate embedding for a query string using default config."""
        return await embed_query(self.db, query)

    async def embed_query_with_model(
        self,
        query: str,
        provider: str,
        model: str
    ) -> list[float]:
        """
        Generate embedding for a query string using a specific provider/model.

        Args:
            query: The text to embed
            provider: Embedding provider name (e.g., "ollama", "openai")
            model: Embedding model name (e.g., "mxbai-embed-large")

        Returns:
            List of floats representing the embedding vector
        """
        return await embed_query_with_model(query, provider, model)

    async def search_multi_embedding(
        self,
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
            query: The search query
            source_ids: List of source IDs to search across
            top_k: Number of results to return
            score_threshold: Minimum score threshold for results

        Returns:
            List of SearchResult objects merged and ranked by RRF score
        """
        return await search_multi_embedding(
            self.db, self.client, query, source_ids, top_k, score_threshold
        )

    async def search(
        self,
        query: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        strict_embedding_match: bool = True,
        source_ids: Optional[list[str]] = None,
        filters: Optional[dict] = None,
        knowledge_base_id: Optional[str] = None,
        rerank: bool = True,
        rerank_model: str = "qwen-reranker-light:latest",
    ) -> list[SearchResult]:
        """
        Search the knowledge base for relevant documents.

        Args:
            query: The search query
            project_id: Optional project to scope search to
            top_k: Number of results to return
            strict_embedding_match: If True, skip sources with different embedding models
            source_ids: Optional list of specific knowledge source IDs to search
            knowledge_base_id: Optional KB ID — resolves to source IDs at query time.
                               Mutually exclusive with source_ids.
            rerank: If True, apply cross-encoder reranking after retrieval (default: True).
                    Pass rerank=False for faster but less precise results.
            rerank_model: Ollama reranker model (only used when rerank=True)

        Returns:
            List of SearchResult objects ranked by relevance (or rerank score)
        """
        # Resolve KB → source IDs if provided (mirrors search_hybrid).
        if knowledge_base_id and source_ids:
            raise ValueError("source_ids and knowledge_base_id are mutually exclusive")
        if knowledge_base_id:
            source_ids = await self._resolve_kb_source_ids(knowledge_base_id)

        # When reranking, fetch a larger candidate pool so the cross-encoder has
        # more documents to work with. This is the "recall first, then rank" pattern:
        # broad retrieval (top_k * 3) → precise ranking (top_k) via cross-encoder.
        retrieval_top_k = top_k * 3 if rerank else top_k

        results = await search_standard(
            self.db, self.client, query, project_id, retrieval_top_k,
            strict_embedding_match, source_ids, filters=filters,
        )

        if rerank and results:
            docs = _results_to_reranker_docs(results)
            reranked = await self._get_reranker().rerank(
                query, docs, model=rerank_model, top_k=top_k
            )
            results = _reranker_docs_to_results(reranked)

        return results

    async def search_hybrid(
        self,
        query: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        vector_weight: float = 0.7,
        filters: Optional[dict] = None,
        source_ids: Optional[list[str]] = None,
        knowledge_base_id: Optional[str] = None,
        rerank: bool = True,
        rerank_model: str = "qwen-reranker-light:latest",
    ) -> list[SearchResult]:
        """
        Hybrid search combining vector similarity and text matching.

        Uses Reciprocal Rank Fusion (RRF) to combine results from:
        - Semantic search (dense vector similarity)
        - Text search (keyword matching via Qdrant text index)

        When qdrant-client >= 1.9.0 is installed, fusion is performed server-side
        via Qdrant's native query API. Otherwise, Python-side weighted RRF is used.

        Args:
            query: The search query
            project_id: Optional project to scope search to
            top_k: Number of results to return
            vector_weight: Weight for vector search (0-1), text weight = 1 - vector_weight
                           (only applies to Python-side RRF fallback)
            source_ids: Optional list of specific knowledge source IDs to search
            knowledge_base_id: Optional KB ID — resolves to source IDs at query time.
                               Mutually exclusive with source_ids.
            rerank: If True, apply cross-encoder reranking after retrieval (default: True).
                    Pass rerank=False for faster but less precise results.
            rerank_model: Ollama reranker model (only used when rerank=True)

        Returns:
            List of SearchResult objects ranked by combined RRF score (or rerank score)
        """
        # Resolve KB → source IDs if provided
        if knowledge_base_id and source_ids:
            raise ValueError("source_ids and knowledge_base_id are mutually exclusive")
        if knowledge_base_id:
            source_ids = await self._resolve_kb_source_ids(knowledge_base_id)

        # When reranking, fetch a larger candidate pool so the cross-encoder has
        # more documents to work with. The RRF fusion then reranks the broader set.
        retrieval_top_k = top_k * 3 if rerank else top_k

        results = await search_hybrid(
            self.db, self.client, query, project_id, retrieval_top_k, vector_weight,
            filters=filters, source_ids=source_ids,
        )

        if rerank and results:
            docs = _results_to_reranker_docs(results)
            reranked = await self._get_reranker().rerank(
                query, docs, model=rerank_model, top_k=top_k
            )
            results = _reranker_docs_to_results(reranked)

        return results

    async def search_grouped(
        self,
        query: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        source_ids: Optional[list[str]] = None,
        filters=None,
        group_size: int = 2,
        rerank: bool = False,
        rerank_model: str = "qwen-reranker-light:latest",
    ) -> list[SearchResult]:
        """
        Search with results grouped by source document.

        Returns at most group_size chunks per unique document (identified by
        metadata.file_id). This prevents a single large document from dominating
        the result set.

        Falls back to search_standard if the Qdrant client or collection does
        not support grouped queries.

        Args:
            query: The search query
            project_id: Optional project to scope search to
            top_k: Number of document groups to return
            source_ids: Optional list of specific knowledge source IDs to search
            filters: Optional Qdrant Filter object for payload filtering
            group_size: Max chunks to return per document group (default 2)
            rerank: If True, apply cross-encoder reranking after retrieval
            rerank_model: Ollama reranker model (only used when rerank=True)

        Returns:
            List of SearchResult objects, at most group_size per unique document.
        """
        results = await search_grouped(
            self.db, self.client, query, project_id, top_k,
            source_ids, filters, group_size
        )

        if rerank and results:
            docs = _results_to_reranker_docs(results)
            reranked = await self._get_reranker().rerank(
                query, docs, model=rerank_model, top_k=top_k * group_size
            )
            results = _reranker_docs_to_results(reranked)

        return results

    async def deep_search(
        self,
        query: str,
        project_id: Optional[str] = None,
        top_k: int = 10,
        max_sub_queries: int = 5,
        filters: Optional[dict] = None,
        source_ids: Optional[list[str]] = None,
        knowledge_base_id: Optional[str] = None,
        rerank: bool = True,
        rerank_model: str = "qwen-reranker-light:latest",
        include_decomposition: bool = False,
    ) -> DeepSearchResult:
        """
        Deep search with automatic query decomposition.

        Breaks a complex query into focused sub-queries, searches each in
        parallel, deduplicates by content_hash, fuses via RRF, and reranks
        against the original query.

        Args:
            query: The complex search query
            project_id: Optional project to scope search to
            top_k: Number of final results to return
            max_sub_queries: Maximum sub-queries from decomposition (excluding original)
            filters: Global metadata filters applied to ALL sub-queries
            source_ids: Optional list of source IDs to search
            knowledge_base_id: Optional KB ID — resolves to source IDs at query time.
                               Mutually exclusive with source_ids.
            rerank: Apply cross-encoder reranking on merged results
            rerank_model: Ollama reranker model
            include_decomposition: Include sub_queries in response

        Returns:
            DeepSearchResult with results, optional sub_queries, and stats
        """
        # Resolve KB → source IDs if provided
        if knowledge_base_id and source_ids:
            raise ValueError("source_ids and knowledge_base_id are mutually exclusive")
        if knowledge_base_id:
            source_ids = await self._resolve_kb_source_ids(knowledge_base_id)

        overall_start = time.monotonic()

        # Load taxonomy vocabulary for decomposition prompt
        taxonomy_vocab = await self._get_taxonomy_vocabulary()

        # Decompose — uses lazy singleton so health check is cached
        sub_queries, decompose_ms = await self._get_decomposer().decompose(
            query,
            max_sub_queries=max_sub_queries,
            taxonomy_vocab=taxonomy_vocab,
        )

        # Merge global filters into each sub-query's filters
        if filters:
            for sq in sub_queries:
                merged = dict(filters)
                merged.update(sq.filters)  # sub-query filters take precedence
                sq.filters = merged

        # Parallel sub-query search — each fetches top_k * 2 candidates, no reranking
        search_start = time.monotonic()

        async def _search_sub(sq: SubQuery) -> list[SearchResult]:
            sq_filters = sq.filters if sq.filters else None
            return await search_hybrid(
                self.db, self.client, sq.query, project_id, top_k * 2,
                vector_weight=0.7, filters=sq_filters, source_ids=source_ids,
            )

        all_results = await asyncio.gather(*[_search_sub(sq) for sq in sub_queries])
        search_ms = (time.monotonic() - search_start) * 1000

        # Shared key function for consistent dedup + RRF score lookup
        def _result_key(r: SearchResult) -> str:
            ch = r.metadata.get("content_hash", "")
            return f"{r.source}:{ch}" if ch else f"{r.source}:{hash(r.content[:200])}"

        # Deduplicate by content_hash — keep the copy with the highest score
        seen: dict[str, SearchResult] = {}
        total_candidates = 0
        for result_list in all_results:
            total_candidates += len(result_list)
            for r in result_list:
                key = _result_key(r)
                if key not in seen or r.score > seen[key].score:
                    seen[key] = r

        deduped = list(seen.values())

        # RRF fusion across sub-query result lists
        if len(all_results) > 1:
            merged = reciprocal_rank_fusion(all_results)
            rrf_scores = {_result_key(r): r.score for r in merged}
            for r in deduped:
                rrf_score = rrf_scores.get(_result_key(r))
                if rrf_score is not None:
                    r.metadata["original_score"] = r.score
                    r.score = rrf_score
                    r.metadata["fusion_method"] = "rrf"

        deduped.sort(key=lambda x: x.score, reverse=True)

        # Rerank against original query
        rerank_ms = 0.0
        if rerank and deduped:
            rerank_start = time.monotonic()
            docs = _results_to_reranker_docs(deduped)
            reranked = await self._get_reranker().rerank(
                query, docs, model=rerank_model, top_k=top_k
            )
            deduped = _reranker_docs_to_results(reranked)
            rerank_ms = (time.monotonic() - rerank_start) * 1000

        final = deduped[:top_k]
        total_ms = (time.monotonic() - overall_start) * 1000

        stats = {
            "sub_query_count": len(sub_queries),
            "total_candidates": total_candidates,
            "deduplicated": len(seen),
            "returned": len(final),
            "decomposition_time_ms": round(decompose_ms, 1),
            "search_time_ms": round(search_ms, 1),
            "rerank_time_ms": round(rerank_ms, 1),
            "total_time_ms": round(total_ms, 1),
        }

        return DeepSearchResult(
            results=final,
            sub_queries=sub_queries if include_decomposition else [],
            stats=stats,
        )

    async def _get_taxonomy_vocabulary(self) -> dict[str, list[str]]:
        """Load taxonomy terms grouped by facet for decomposition prompts.

        Returns dict like {"platforms": ["AcmeCRM", "WidgetHub"], "products": [...]}
        Scans all taxonomies — vocabulary is a union of all terms.
        """
        from app.models import Taxonomy, TaxonomyTerm
        from sqlalchemy.orm import selectinload

        try:
            stmt = select(Taxonomy).options(selectinload(Taxonomy.terms))
            result = await self.db.execute(stmt)
            taxonomies = result.scalars().all()

            vocab: dict[str, list[str]] = {}
            for tax in taxonomies:
                for term in tax.terms:
                    facet = term.facet
                    if facet not in vocab:
                        vocab[facet] = []
                    if term.value not in vocab[facet]:
                        vocab[facet].append(term.value)

            return vocab
        except Exception as e:
            logger.warning("Failed to load taxonomy vocabulary", error=str(e))
            return {}

    async def get_context_for_query(
        self,
        query: str,
        project_id: Optional[str] = None,
        top_k: int = 5,
        source_ids: Optional[list[str]] = None,
    ) -> RAGContext:
        """
        Get formatted context for a query, ready for LLM injection.

        Args:
            query: The user's query
            project_id: Optional project scope
            top_k: Number of results to retrieve (this governs context size)
            source_ids: Optional list of specific source IDs to search (for agent-bound sources)

        Returns:
            RAGContext with formatted text and source attribution
        """
        return await get_context_for_query(
            self.db, self.client, query, project_id, top_k, source_ids
        )
