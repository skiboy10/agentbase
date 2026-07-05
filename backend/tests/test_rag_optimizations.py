"""
Tests for RAG algorithmic optimizations (GitHub issue #26):
- Group-by-document search (search_grouped)
- Reranking service (RerankerService)
- RAGService facade integration (rerank param, search_grouped)
- Helper conversion functions

All Qdrant and HTTP calls are mocked — no live services required.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.rag.reranker import RerankerService
from app.services.rag.service import (
    RAGService,
    _results_to_reranker_docs,
    _reranker_docs_to_results,
)
from app.services.rag.types import SearchResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_search_result(content="test content", source="https://example.com",
                        score=0.8, **meta) -> SearchResult:
    """Build a SearchResult for testing."""
    return SearchResult(
        content=content,
        source=source,
        score=score,
        metadata={
            "source_id": meta.get("source_id", "src-1"),
            "chunk_index": meta.get("chunk_index", 0),
            "source_name": meta.get("source_name", "Test Source"),
            "title": meta.get("title", ""),
            **{k: v for k, v in meta.items()
               if k not in ("source_id", "chunk_index", "source_name", "title")},
        }
    )


# ---------------------------------------------------------------------------
# Helper conversion functions
# ---------------------------------------------------------------------------

class TestResultConversions:
    """Tests for _results_to_reranker_docs and _reranker_docs_to_results."""

    def test_results_to_reranker_docs_basic(self):
        results = [make_search_result(content="doc a", score=0.9)]
        docs = _results_to_reranker_docs(results)

        assert len(docs) == 1
        assert docs[0]["content"] == "doc a"
        assert docs[0]["source"] == "https://example.com"
        assert docs[0]["score"] == 0.9
        assert docs[0]["source_id"] == "src-1"

    def test_results_to_reranker_docs_does_not_mutate_original(self):
        r = make_search_result()
        original_metadata = dict(r.metadata)
        _results_to_reranker_docs([r])
        assert r.metadata == original_metadata  # no mutation

    def test_reranker_docs_to_results_uses_rerank_score(self):
        docs = [
            {"content": "doc a", "source": "url-a", "score": 0.3,
             "_rerank_score": 0.95, "source_id": "src-1"},
        ]
        results = _reranker_docs_to_results(docs)

        assert len(results) == 1
        assert results[0].score == 0.95  # rerank score wins
        assert results[0].metadata["original_score"] == 0.3  # original preserved

    def test_reranker_docs_to_results_falls_back_to_original_score(self):
        docs = [
            {"content": "doc a", "source": "url-a", "score": 0.7,
             "source_id": "src-1"},  # no _rerank_score
        ]
        results = _reranker_docs_to_results(docs)
        assert results[0].score == 0.7

    def test_reranker_docs_to_results_does_not_mutate_input(self):
        doc = {"content": "doc a", "source": "url-a", "score": 0.5,
               "_rerank_score": 0.9, "source_id": "src-1"}
        original = dict(doc)
        _reranker_docs_to_results([doc])
        assert doc == original  # must not mutate the input dict

    def test_roundtrip_preserves_metadata(self):
        r = make_search_result(content="important doc", score=0.75, title="My Doc")
        docs = _results_to_reranker_docs([r])
        docs[0]["_rerank_score"] = 0.95  # simulate reranker adding score
        back = _reranker_docs_to_results(docs)

        assert back[0].content == "important doc"
        assert back[0].metadata["title"] == "My Doc"
        assert back[0].score == 0.95


# ---------------------------------------------------------------------------
# RerankerService
# ---------------------------------------------------------------------------

class TestRerankerService:
    """Tests for the RerankerService."""

    @pytest.mark.asyncio
    async def test_rerank_returns_unchanged_on_empty_input(self):
        reranker = RerankerService()
        result = await reranker.rerank("query", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_rerank_success(self):
        """Reranker returns documents sorted by score."""
        docs = [
            {"content": "doc A", "source": "url-a"},
            {"content": "doc B", "source": "url-b"},
            {"content": "doc C", "source": "url-c"},
        ]

        def mock_flashrank(query, documents, top_k):
            scored = [dict(d) for d in documents]
            scores = [0.4, 0.9, 0.6]
            for d, s in zip(scored, scores):
                d["_rerank_score"] = s
            scored.sort(key=lambda x: x["_rerank_score"], reverse=True)
            return scored[:top_k] if top_k else scored

        reranker = RerankerService()
        reranker._available = True
        reranker._backend = "flashrank"
        with patch.object(reranker, "_rerank_flashrank", side_effect=mock_flashrank):
            result = await reranker.rerank("test query", docs)

        # Should be sorted: doc B (0.9) > doc C (0.6) > doc A (0.4)
        assert result[0]["content"] == "doc B"
        assert result[0]["_rerank_score"] == 0.9
        assert result[1]["content"] == "doc C"
        assert result[2]["content"] == "doc A"

    @pytest.mark.asyncio
    async def test_rerank_top_k_truncation(self):
        """top_k limits the number of returned documents."""
        docs = [{"content": f"doc {i}", "source": f"url-{i}"} for i in range(5)]

        def mock_flashrank(query, documents, top_k):
            scores = [0.5, 0.9, 0.3, 0.8, 0.1]
            scored = [dict(d) for d in documents]
            for d, s in zip(scored, scores):
                d["_rerank_score"] = s
            scored.sort(key=lambda x: x["_rerank_score"], reverse=True)
            return scored[:top_k] if top_k else scored

        reranker = RerankerService()
        reranker._available = True
        reranker._backend = "flashrank"
        with patch.object(reranker, "_rerank_flashrank", side_effect=mock_flashrank):
            result = await reranker.rerank("test query", docs, top_k=2)

        assert len(result) == 2
        assert result[0]["_rerank_score"] == 0.9
        assert result[1]["_rerank_score"] == 0.8

    @pytest.mark.asyncio
    async def test_rerank_graceful_degradation_on_failure(self):
        """On backend failure, documents are returned unchanged in original order."""
        docs = [
            {"content": "doc A", "source": "url-a"},
            {"content": "doc B", "source": "url-b"},
        ]

        reranker = RerankerService()
        reranker._available = True
        reranker._backend = "flashrank"
        with patch.object(reranker, "_rerank_flashrank",
                          side_effect=RuntimeError("model not available")):
            result = await reranker.rerank("test query", docs)

        # Should return original docs unchanged (no _rerank_score added)
        assert len(result) == 2
        assert result[0]["content"] == "doc A"
        assert "_rerank_score" not in result[0]

    @pytest.mark.asyncio
    async def test_rerank_does_not_mutate_input_docs(self):
        """Input document list and dicts must not be mutated."""
        original_doc = {"content": "doc A", "source": "url-a"}
        docs = [original_doc]

        def mock_flashrank(query, documents, top_k):
            scored = [dict(d) for d in documents]
            scored[0]["_rerank_score"] = 0.7
            return scored

        reranker = RerankerService()
        reranker._available = True
        reranker._backend = "flashrank"
        with patch.object(reranker, "_rerank_flashrank", side_effect=mock_flashrank):
            await reranker.rerank("test query", docs)

        # Original doc dict must be unchanged
        assert "_rerank_score" not in original_doc

    @pytest.mark.asyncio
    async def test_rerank_skipped_when_model_unavailable(self):
        """When model health check fails, documents are returned in original order."""
        docs = [
            {"content": "doc A", "source": "url-a"},
            {"content": "doc B", "source": "url-b"},
        ]

        reranker = RerankerService()
        with patch.object(reranker, "_ensure_available", new=AsyncMock(return_value=False)):
            result = await reranker.rerank("test query", docs)

        # Should return original docs unchanged when model not available
        assert result == docs
        assert "_rerank_score" not in result[0]

    @pytest.mark.asyncio
    async def test_is_available_returns_false_when_no_backend(self):
        """is_available() returns False when no reranker backend is available."""
        reranker = RerankerService()
        with patch.object(reranker, "_ensure_flashrank", return_value=False), \
             patch.object(reranker, "_check_ollama_rerank", new=AsyncMock(return_value=False)):
            result = await reranker.is_available()
        assert result is False


# ---------------------------------------------------------------------------
# RAGService — rerank integration
# ---------------------------------------------------------------------------

class TestRAGServiceRerankIntegration:
    """Tests for rerank= parameter on RAGService search methods."""

    def _make_mock_db(self):
        return AsyncMock(spec=AsyncSession)

    def _make_mock_qdrant(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_search_without_rerank_does_not_call_reranker(self):
        """When rerank=False, RerankerService is never instantiated."""
        mock_results = [make_search_result()]

        with patch("app.services.rag.service.search_standard", new=AsyncMock(return_value=mock_results)), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(self._make_mock_db())
            svc._reranker = MagicMock()  # inject a spy

            results = await svc.search("test query", rerank=False)

        # Reranker's rerank method should NOT have been called
        svc._reranker.rerank.assert_not_called()
        assert results == mock_results

    @pytest.mark.asyncio
    async def test_search_with_rerank_calls_reranker(self):
        """When rerank=True, results are passed through the reranker."""
        mock_results = [
            make_search_result(content="low score doc", score=0.5),
            make_search_result(content="high score doc", score=0.9),
        ]

        # Simulate reranker flipping the order
        reranked_docs = [
            {"content": "low score doc", "source": "url", "score": 0.5, "_rerank_score": 0.95},
            {"content": "high score doc", "source": "url", "score": 0.9, "_rerank_score": 0.3},
        ]

        with patch("app.services.rag.service.search_standard", new=AsyncMock(return_value=mock_results)), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(self._make_mock_db())
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=reranked_docs)
            svc._reranker = mock_reranker

            results = await svc.search("test query", rerank=True)

        # Verify reranker was called with the right query
        mock_reranker.rerank.assert_called_once()
        call_args = mock_reranker.rerank.call_args
        assert call_args[0][0] == "test query"  # first positional arg is query

        # Result should use rerank scores
        assert results[0].content == "low score doc"
        assert results[0].score == 0.95

    @pytest.mark.asyncio
    async def test_search_with_rerank_empty_results_skips_reranker(self):
        """When search returns empty, reranker is not called."""
        with patch("app.services.rag.service.search_standard", new=AsyncMock(return_value=[])), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(self._make_mock_db())
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock()
            svc._reranker = mock_reranker

            results = await svc.search("test query", rerank=True)

        mock_reranker.rerank.assert_not_called()
        assert results == []

    @pytest.mark.asyncio
    async def test_search_with_rerank_fetches_expanded_candidate_pool(self):
        """When rerank=True, search_standard is called with top_k * 3 candidates."""
        mock_results = [make_search_result()]
        reranked_docs = [
            {"content": mock_results[0].content, "source": mock_results[0].source,
             "score": mock_results[0].score, "_rerank_score": 0.99}
        ]

        mock_search_standard = AsyncMock(return_value=mock_results)

        with patch("app.services.rag.service.search_standard", new=mock_search_standard), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(self._make_mock_db())
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=reranked_docs)
            svc._reranker = mock_reranker

            await svc.search("test query", top_k=5, rerank=True)

        # The retrieval call should use top_k * 3 = 15
        call_args = mock_search_standard.call_args
        retrieval_top_k = call_args[0][4]  # 5th positional arg is top_k to search_standard
        assert retrieval_top_k == 15

    @pytest.mark.asyncio
    async def test_search_without_rerank_uses_exact_top_k(self):
        """When rerank=False, search_standard is called with the exact top_k."""
        mock_results = [make_search_result()]
        mock_search_standard = AsyncMock(return_value=mock_results)

        with patch("app.services.rag.service.search_standard", new=mock_search_standard), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(self._make_mock_db())
            await svc.search("test query", top_k=5, rerank=False)

        call_args = mock_search_standard.call_args
        retrieval_top_k = call_args[0][4]  # 5th positional arg is top_k
        assert retrieval_top_k == 5

    @pytest.mark.asyncio
    async def test_search_hybrid_with_rerank_calls_reranker(self):
        """search_hybrid with rerank=True passes results through the reranker."""
        mock_results = [
            make_search_result(content="hybrid result", score=0.7),
        ]
        reranked_docs = [
            {"content": "hybrid result", "source": "url", "score": 0.7, "_rerank_score": 0.92}
        ]

        with patch("app.services.rag.service.search_hybrid", new=AsyncMock(return_value=mock_results)), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(self._make_mock_db())
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=reranked_docs)
            svc._reranker = mock_reranker

            results = await svc.search_hybrid("test query", rerank=True)

        mock_reranker.rerank.assert_called_once()
        assert results[0].score == 0.92

    @pytest.mark.asyncio
    async def test_search_hybrid_with_rerank_fetches_expanded_candidate_pool(self):
        """When rerank=True, search_hybrid is called with top_k * 3 candidates."""
        mock_results = [make_search_result()]
        reranked_docs = [
            {"content": mock_results[0].content, "source": mock_results[0].source,
             "score": mock_results[0].score, "_rerank_score": 0.95}
        ]

        mock_search_hybrid = AsyncMock(return_value=mock_results)

        with patch("app.services.rag.service.search_hybrid", new=mock_search_hybrid), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(self._make_mock_db())
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=reranked_docs)
            svc._reranker = mock_reranker

            await svc.search_hybrid("test query", top_k=5, rerank=True)

        # The retrieval call should use top_k * 3 = 15
        call_args = mock_search_hybrid.call_args
        retrieval_top_k = call_args[0][4]  # 5th positional arg is top_k to search_hybrid
        assert retrieval_top_k == 15


# ---------------------------------------------------------------------------
# RAGService — search_grouped
# ---------------------------------------------------------------------------

class TestRAGServiceSearchGrouped:
    """Tests for RAGService.search_grouped()."""

    @pytest.mark.asyncio
    async def test_search_grouped_delegates_to_search_grouped_function(self):
        """search_grouped() correctly delegates to the search module function."""
        mock_results = [make_search_result()]

        with patch("app.services.rag.service.search_grouped", new=AsyncMock(return_value=mock_results)) as mock_fn, \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(AsyncMock(spec=AsyncSession))
            results = await svc.search_grouped(
                "test query",
                project_id="proj-1",
                top_k=3,
                group_size=2,
            )

        mock_fn.assert_called_once()
        call_kwargs = mock_fn.call_args
        assert call_kwargs[0][2] == "test query"  # query arg
        assert results == mock_results

    @pytest.mark.asyncio
    async def test_search_grouped_with_rerank(self):
        """search_grouped reranks results when rerank=True."""
        mock_results = [make_search_result(content="result 1", score=0.6)]
        reranked = [{"content": "result 1", "source": "url", "score": 0.6, "_rerank_score": 0.99}]

        with patch("app.services.rag.service.search_grouped", new=AsyncMock(return_value=mock_results)), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(AsyncMock(spec=AsyncSession))
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=reranked)
            svc._reranker = mock_reranker

            results = await svc.search_grouped("test query", group_size=2, rerank=True)

        mock_reranker.rerank.assert_called_once()
        assert results[0].score == 0.99


# ---------------------------------------------------------------------------
# RAGService — knowledge_base_id resolution (#71)
# ---------------------------------------------------------------------------

class TestKnowledgeBaseResolution:
    """Tests for knowledge_base_id → source_ids resolution."""

    @pytest.mark.asyncio
    async def test_resolve_kb_source_ids_success(self):
        """Valid KB returns its source IDs."""
        mock_kb = MagicMock()
        mock_kb.name = "Work Documents"
        mock_kb.sources = [
            MagicMock(id="src-1"),
            MagicMock(id="src-2"),
            MagicMock(id="src-3"),
        ]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_kb
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):
            svc = RAGService(mock_db)
            source_ids = await svc._resolve_kb_source_ids("kb-123")

        assert source_ids == ["src-1", "src-2", "src-3"]

    @pytest.mark.asyncio
    async def test_resolve_kb_source_ids_not_found(self):
        """Missing KB raises ValueError."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):
            svc = RAGService(mock_db)
            with pytest.raises(ValueError, match="not found"):
                await svc._resolve_kb_source_ids("nonexistent-kb")

    @pytest.mark.asyncio
    async def test_resolve_kb_source_ids_empty_sources(self):
        """KB with no sources raises ValueError."""
        mock_kb = MagicMock()
        mock_kb.name = "Empty KB"
        mock_kb.sources = []

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_kb
        mock_db = AsyncMock(spec=AsyncSession)
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):
            svc = RAGService(mock_db)
            with pytest.raises(ValueError, match="has no sources"):
                await svc._resolve_kb_source_ids("empty-kb")

    @pytest.mark.asyncio
    async def test_deep_search_with_kb_id_resolves_sources(self):
        """deep_search with knowledge_base_id calls _resolve_kb_source_ids."""
        mock_results = [make_search_result()]

        with patch("app.services.rag.service.search_hybrid", new=AsyncMock(return_value=mock_results)), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(AsyncMock(spec=AsyncSession))
            svc._resolve_kb_source_ids = AsyncMock(return_value=["src-1", "src-2"])
            svc._get_decomposer = MagicMock()
            svc._get_decomposer().decompose = AsyncMock(return_value=(
                [MagicMock(query="test", filters={}, strategy="original")],
                10.0,
            ))
            svc._get_taxonomy_vocabulary = AsyncMock(return_value={})
            mock_reranker = MagicMock()
            mock_reranker.rerank = AsyncMock(return_value=[
                {"content": "test content", "source": "url", "score": 0.8, "_rerank_score": 0.95}
            ])
            svc._reranker = mock_reranker

            result = await svc.deep_search("test query", knowledge_base_id="kb-123")

        svc._resolve_kb_source_ids.assert_called_once_with("kb-123")

    @pytest.mark.asyncio
    async def test_search_hybrid_with_kb_id_resolves_sources(self):
        """search_hybrid with knowledge_base_id calls _resolve_kb_source_ids."""
        mock_results = [make_search_result()]

        with patch("app.services.rag.service.search_hybrid", new=AsyncMock(return_value=mock_results)), \
             patch("app.services.rag.service.get_qdrant_client", return_value=MagicMock()), \
             patch("app.services.rag.service.get_embedding_registry", return_value=MagicMock()):

            svc = RAGService(AsyncMock(spec=AsyncSession))
            svc._resolve_kb_source_ids = AsyncMock(return_value=["src-1", "src-2"])

            await svc.search_hybrid("test query", knowledge_base_id="kb-123", rerank=False)

        svc._resolve_kb_source_ids.assert_called_once_with("kb-123")


class TestSearchRequestValidation:
    """Tests for mutual exclusion of source_ids and knowledge_base_id."""

    def test_search_request_allows_source_ids_only(self):
        from app.api.sources.schemas import SearchRequest
        req = SearchRequest(query="test", source_ids=["src-1"])
        assert req.source_ids == ["src-1"]
        assert req.knowledge_base_id is None

    def test_search_request_allows_kb_id_only(self):
        from app.api.sources.schemas import SearchRequest
        req = SearchRequest(query="test", knowledge_base_id="kb-1")
        assert req.knowledge_base_id == "kb-1"
        assert req.source_ids is None

    def test_search_request_rejects_both(self):
        from app.api.sources.schemas import SearchRequest
        with pytest.raises(Exception, match="mutually exclusive"):
            SearchRequest(query="test", source_ids=["src-1"], knowledge_base_id="kb-1")

    def test_deep_search_request_rejects_both(self):
        from app.api.sources.schemas import DeepSearchRequest
        with pytest.raises(Exception, match="mutually exclusive"):
            DeepSearchRequest(query="test", source_ids=["src-1"], knowledge_base_id="kb-1")

    def test_deep_search_request_allows_kb_id_only(self):
        from app.api.sources.schemas import DeepSearchRequest
        req = DeepSearchRequest(query="test", knowledge_base_id="kb-1")
        assert req.knowledge_base_id == "kb-1"


# ---------------------------------------------------------------------------
# Capability detection (smoke test — verifies module imports cleanly)
# ---------------------------------------------------------------------------

class TestCapabilityDetection:
    """Verify that the module-level capability flags are booleans and don't crash."""

    def test_capability_flags_are_booleans(self):
        from app.services.rag import search as search_module
        assert isinstance(search_module._SUPPORTS_NATIVE_FUSION, bool)
        assert isinstance(search_module._SUPPORTS_QUERY_GROUPS, bool)

    def test_capability_detection_runs(self):
        from app.services.rag import search as search_module
        # Capability flags set regardless of qdrant-client version
        assert hasattr(search_module, '_SUPPORTS_NATIVE_FUSION')
        assert hasattr(search_module, '_SUPPORTS_QUERY_GROUPS')
