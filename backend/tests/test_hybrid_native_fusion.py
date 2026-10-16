"""Tests for native Qdrant hybrid fusion + sparse BM25 schema helpers (#33)."""
from unittest.mock import MagicMock

from qdrant_client.models import Document

from app.services.rag import collection_schema as schema
from app.services.rag import search as search_module


def test_native_fusion_enabled_with_current_client():
    assert search_module._SUPPORTS_NATIVE_FUSION is True


def test_content_text_index_has_stemming_and_stopwords():
    params = schema.content_text_index_params()
    assert params.stopwords is not None
    assert params.stemmer is not None
    assert params.phrase_matching is True


def test_point_vectors_dense_only():
    dense = [0.1, 0.2, 0.3]
    assert schema.point_vectors(dense, "hello", include_sparse=False) == dense


def test_point_vectors_includes_bm25_document():
    dense = [0.1, 0.2]
    vectors = schema.point_vectors(dense, "acme playbook", include_sparse=True)
    assert vectors[""] == dense
    assert schema.SPARSE_BM25_NAME in vectors
    doc = vectors[schema.SPARSE_BM25_NAME]
    assert isinstance(doc, Document)
    assert doc.model == schema.BM25_MODEL
    assert doc.text == "acme playbook"


def test_collection_has_sparse_bm25_true():
    client = MagicMock()
    client.get_collection.return_value.config.params.sparse_vectors = {
        schema.SPARSE_BM25_NAME: object(),
    }
    assert schema.collection_has_sparse_bm25(client, "c1") is True


def test_collection_has_sparse_bm25_false():
    client = MagicMock()
    client.get_collection.return_value.config.params.sparse_vectors = {}
    assert schema.collection_has_sparse_bm25(client, "c1") is False


def test_ensure_sparse_bm25_updates_when_missing():
    client = MagicMock()
    client.get_collection.return_value.config.params.sparse_vectors = {}
    assert schema.ensure_sparse_bm25(client, "c1") is True
    client.update_collection.assert_called_once()
    kwargs = client.update_collection.call_args.kwargs
    assert schema.SPARSE_BM25_NAME in kwargs["sparse_vectors_config"]


def test_create_hybrid_collection_passes_sparse_config():
    client = MagicMock()
    schema.create_hybrid_collection(client, "c1", 384)
    kwargs = client.create_collection.call_args.kwargs
    assert kwargs["collection_name"] == "c1"
    assert schema.SPARSE_BM25_NAME in kwargs["sparse_vectors_config"]


def test_native_hybrid_uses_bm25_prefetch_when_schema_present():
    """_search_hybrid_native should Prefetch dense + BM25 Document when sparse exists."""
    import asyncio
    from app.services.rag.types import SearchResult

    source = MagicMock()
    source.id = "src-1"
    source.name = "Acme Docs"
    source.collection_name = "col-1"

    hit = MagicMock()
    hit.score = 0.9
    hit.payload = {
        "content": "hello",
        "source": "/tmp/acme.md",
        "title": "Acme",
        "source_id": "src-1",
        "chunk_index": 0,
    }
    response = MagicMock()
    response.points = [hit]

    client = MagicMock()
    client.query_points.return_value = response
    client.get_collection.return_value.config.params.sparse_vectors = {
        schema.SPARSE_BM25_NAME: object(),
    }

    results = asyncio.run(
        search_module._search_hybrid_native(
            client,
            [source],
            query_embedding=[0.1, 0.2],
            query_text="acme",
            top_k=5,
        )
    )

    assert len(results) == 1
    assert isinstance(results[0], SearchResult)
    assert results[0].metadata["fusion_method"] == "native_rrf_bm25"
    call_kwargs = client.query_points.call_args.kwargs
    assert len(call_kwargs["prefetch"]) == 2
    sparse_prefetch = call_kwargs["prefetch"][1]
    assert sparse_prefetch.using == schema.SPARSE_BM25_NAME
    assert isinstance(sparse_prefetch.query, Document)


def test_native_hybrid_falls_back_to_match_text_without_sparse():
    import asyncio

    source = MagicMock()
    source.id = "src-1"
    source.name = "Acme Docs"
    source.collection_name = "col-legacy"

    response = MagicMock()
    response.points = []
    client = MagicMock()
    client.query_points.return_value = response
    client.get_collection.return_value.config.params.sparse_vectors = {}

    asyncio.run(
        search_module._search_hybrid_native(
            client,
            [source],
            query_embedding=[0.1],
            query_text="acme",
            top_k=3,
        )
    )

    call_kwargs = client.query_points.call_args.kwargs
    assert len(call_kwargs["prefetch"]) == 2
    # Second branch is dense + MatchText filter (no using=bm25)
    assert call_kwargs["prefetch"][1].using is None
