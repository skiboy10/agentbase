"""
Embedding Processor - Shared embedding and Qdrant upsert logic.

This module provides:
- Qdrant client singleton
- Batch embedding generation
- Chunk upsert to Qdrant
- Text chunking with LangChain
"""
import hashlib
from typing import Optional
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, TextIndexParams, TextIndexType, TokenizerType
import structlog

from app.core.config import get_settings
from app.providers.embedding_registry import get_embedding_registry
from app.services.rag.filters import KEYWORD_INDEX_FIELDS

settings = get_settings()
logger = structlog.get_logger()


# Qdrant client singleton
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """Get or create Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
        )
    return _qdrant_client


class EmbeddingProcessor:
    """
    Handles embedding generation and Qdrant operations.

    Shared by all indexers (directory, file, URL).
    """

    def __init__(self):
        self.client = get_qdrant_client()
        self.embedding_registry = get_embedding_registry()

    def generate_collection_name(self, source_id: str) -> str:
        """Generate a Qdrant collection name for a knowledge source."""
        return f"{settings.qdrant_collection_prefix}{source_id}"

    def compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash of content for change detection."""
        return hashlib.sha256(content.encode()).hexdigest()

    def create_collection(self, collection_name: str, vector_size: int) -> None:
        """Create a Qdrant collection with vector and text index."""
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

        # Add text index for hybrid search
        try:
            self.client.create_payload_index(
                collection_name=collection_name,
                field_name="content",
                field_schema=TextIndexParams(
                    type=TextIndexType.TEXT,
                    tokenizer=TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=20,
                    lowercase=True,
                )
            )
            logger.info("Created text index for hybrid search", collection=collection_name)
        except Exception as e:
            logger.warning("Failed to create text index", collection=collection_name, error=str(e))

        # Add keyword indexes on metadata fields for filtered search
        self._create_keyword_indexes(collection_name)

    def ensure_text_index(self, collection_name: str) -> None:
        """Add text index and keyword indexes to existing collection if not present."""
        try:
            collection_info = self.client.get_collection(collection_name)
            # Check if content field has text index
            payload_schema = collection_info.payload_schema or {}
            if "content" not in payload_schema:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name="content",
                    field_schema=TextIndexParams(
                        type=TextIndexType.TEXT,
                        tokenizer=TokenizerType.WORD,
                        min_token_len=2,
                        max_token_len=20,
                        lowercase=True,
                    )
                )
                logger.info("Added text index to existing collection", collection=collection_name)
        except Exception as e:
            logger.warning("Failed to ensure text index", collection=collection_name, error=str(e))

        # Ensure keyword indexes are present too
        self._create_keyword_indexes(collection_name)

    def _create_keyword_indexes(self, collection_name: str) -> None:
        """Create keyword payload indexes for metadata-filtered search."""
        for field_name, field_schema in KEYWORD_INDEX_FIELDS:
            try:
                self.client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                )
            except Exception:
                # Index may already exist — safe to ignore
                pass
        logger.info("Ensured keyword indexes on collection", collection=collection_name)

    def collection_exists(self, collection_name: str) -> bool:
        """Check if a Qdrant collection exists."""
        try:
            collections = self.client.get_collections().collections
            return any(c.name == collection_name for c in collections)
        except Exception:
            return False

    def delete_collection(self, collection_name: str) -> bool:
        """Delete a Qdrant collection."""
        try:
            self.client.delete_collection(collection_name)
            return True
        except Exception as e:
            logger.warning("Failed to delete collection", collection=collection_name, error=str(e))
            return False

    def get_collection_count(self, collection_name: str) -> int:
        """Get the number of points in a collection."""
        try:
            info = self.client.get_collection(collection_name)
            return info.points_count
        except Exception:
            return 0

    async def process_batch(
        self,
        collection_name: str,
        chunks: list[str],
        metadata: list[dict],
        provider: str,
        model: str,
    ) -> int:
        """
        Process a batch of chunks, generate embeddings, and upsert to Qdrant.

        Args:
            collection_name: Target Qdrant collection
            chunks: List of text chunks to embed
            metadata: List of metadata dicts (one per chunk)
            provider: Embedding provider name
            model: Embedding model name

        Returns:
            Number of points upserted
        """
        response = await self.embedding_registry.embed(provider, model, chunks)
        current_time = datetime.utcnow().isoformat()
        embedding_model_id = f"{provider}/{model}"

        points = []
        for embedding, chunk, meta in zip(response.embeddings, chunks, metadata):
            payload = {
                # Core content
                "content": chunk,
                "source": meta["source"],
                "source_id": meta["source_id"],
                "chunk_index": meta["chunk_index"],
                "title": meta.get("title", ""),
                # Change detection and auditing
                "content_hash": self.compute_content_hash(chunk),
                "scraped_at": meta.get("scraped_at", current_time),
                "embedding_model": embedding_model_id,
                # Extensible metadata
                "metadata": meta.get("metadata", {}),
            }
            # Merge structured metadata into root payload for Qdrant filtering
            default_metadata = meta.get("default_metadata")
            if default_metadata:
                _reserved = {"content", "source", "source_id", "chunk_index", "title",
                             "content_hash", "scraped_at", "embedding_model", "metadata"}
                for key, value in default_metadata.items():
                    if key not in _reserved:
                        payload[key] = value
            points.append(PointStruct(id=meta["id"], vector=embedding, payload=payload))

        self.client.upsert(collection_name=collection_name, points=points)
        return len(points)

    def get_text_splitter(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        """Get a LangChain text splitter configured for document chunking."""
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
