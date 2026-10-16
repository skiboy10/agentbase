"""
Qdrant collection schema helpers for hybrid dense + sparse BM25 (#33).

New collections get:
- Unnamed dense cosine vectors (unchanged contract for existing search paths)
- Named sparse vector ``bm25`` with IDF modifier (server-side BM25 via Document)
- Full-text ``content`` index with English stopwords + Snowball stemming

Existing collections can gain the sparse schema via ``ensure_sparse_bm25``;
points only receive BM25 vectors on the next re-index / upsert.
"""
from __future__ import annotations

from typing import Any, Union

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    Document,
    Language,
    Modifier,
    Snowball,
    SnowballLanguage,
    SnowballParams,
    SparseVectorParams,
    TextIndexParams,
    TextIndexType,
    TokenizerType,
    VectorParams,
)
import structlog

logger = structlog.get_logger()

SPARSE_BM25_NAME = "bm25"
BM25_MODEL = "Qdrant/bm25"


def content_text_index_params() -> TextIndexParams:
    """Full-text index for ``content`` with stemming + English stopwords."""
    return TextIndexParams(
        type=TextIndexType.TEXT,
        tokenizer=TokenizerType.WORD,
        min_token_len=2,
        max_token_len=40,
        lowercase=True,
        stopwords=Language.ENGLISH,
        stemmer=SnowballParams(
            type=Snowball.SNOWBALL,
            language=SnowballLanguage.ENGLISH,
        ),
        phrase_matching=True,
    )


def sparse_bm25_params() -> dict[str, SparseVectorParams]:
    return {SPARSE_BM25_NAME: SparseVectorParams(modifier=Modifier.IDF)}


def create_hybrid_collection(
    client: QdrantClient,
    collection_name: str,
    vector_size: int,
    *,
    with_text_index: bool = True,
) -> None:
    """Create a collection with dense + sparse BM25 vector configs."""
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        sparse_vectors_config=sparse_bm25_params(),
    )
    if with_text_index:
        ensure_content_text_index(client, collection_name)


def ensure_content_text_index(client: QdrantClient, collection_name: str) -> None:
    """Create the ``content`` full-text payload index when missing."""
    try:
        info = client.get_collection(collection_name)
        payload_schema = getattr(info, "payload_schema", None) or {}
        if "content" in payload_schema:
            return
        client.create_payload_index(
            collection_name=collection_name,
            field_name="content",
            field_schema=content_text_index_params(),
        )
        logger.info("Created content text index", collection=collection_name)
    except Exception as e:
        logger.warning(
            "Failed to ensure content text index",
            collection=collection_name,
            error=str(e),
        )


def collection_has_sparse_bm25(client: QdrantClient, collection_name: str) -> bool:
    """Return True when the collection declares the named ``bm25`` sparse vector."""
    try:
        info = client.get_collection(collection_name)
        params = getattr(getattr(info, "config", None), "params", None)
        sparse = getattr(params, "sparse_vectors", None) or {}
        return SPARSE_BM25_NAME in sparse
    except Exception as e:
        logger.debug(
            "Could not inspect sparse vectors on collection",
            collection=collection_name,
            error=str(e),
        )
        return False


def ensure_sparse_bm25(client: QdrantClient, collection_name: str) -> bool:
    """
    Ensure ``bm25`` sparse vector exists on an existing collection.

    Returns True if the schema already had it or was updated successfully.
    Existing points remain without sparse vectors until re-upserted.
    """
    if collection_has_sparse_bm25(client, collection_name):
        return True
    try:
        client.update_collection(
            collection_name=collection_name,
            sparse_vectors_config=sparse_bm25_params(),
        )
        logger.info("Added sparse BM25 vector schema", collection=collection_name)
        return True
    except Exception as e:
        logger.warning(
            "Failed to add sparse BM25 schema",
            collection=collection_name,
            error=str(e),
        )
        return False


def point_vectors(
    dense: list[float],
    text: str,
    *,
    include_sparse: bool = True,
) -> Union[list[float], dict[str, Any]]:
    """
    Build the ``PointStruct.vector`` value for upsert.

    When ``include_sparse`` is True, returns a map with the unnamed dense
    vector (empty-string key) plus a server-inferred BM25 ``Document``.
    Otherwise returns the dense list alone (legacy collections).
    """
    if not include_sparse:
        return dense
    return {
        "": dense,
        SPARSE_BM25_NAME: Document(text=text, model=BM25_MODEL),
    }


def bm25_query_document(query_text: str) -> Document:
    """Query-side BM25 Document for Prefetch (must match upsert model)."""
    return Document(text=query_text, model=BM25_MODEL)
