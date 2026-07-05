"""
Per-document Qdrant operations.

Provides surgical chunk management scoped to individual documents (identified by
their source URL/path) or entire sources within a knowledge source's collection.
These operations support the per-document lifecycle: delete, count, and metadata
retrieval — without touching the rest of the collection.
"""
from typing import Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
import structlog

from .qdrant_client import get_qdrant_client

logger = structlog.get_logger()


class DocumentOps:
    """
    Qdrant operations scoped to individual documents within a source's collection.

    In the current schema, a "document" is identified by the ``source`` payload
    field (URL for web sources, file path for file/directory sources).  All chunks
    from the same URL/path share that value, so filtering on it targets exactly one
    logical document.
    """

    def __init__(self, client: Optional[QdrantClient] = None):
        self.client = client or get_qdrant_client()

    # ------------------------------------------------------------------
    # Per-document operations (keyed by source URL / file path)
    # ------------------------------------------------------------------

    async def delete_document_chunks(
        self, collection_name: str, document_source: str
    ) -> int:
        """
        Delete all chunks for a document from Qdrant.

        Args:
            collection_name: The Qdrant collection that holds the document.
            document_source: The ``source`` payload value — URL or file path —
                             that identifies the document.

        Returns:
            Number of chunks deleted (best-effort from scroll count).
        """
        # Count first so we can report back
        deleted = await self.count_document_chunks(collection_name, document_source)

        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source",
                            match=MatchValue(value=document_source),
                        )
                    ]
                ),
            )
            logger.info(
                "Deleted document chunks",
                collection=collection_name,
                document_source=document_source,
                count=deleted,
            )
        except Exception as e:
            logger.error(
                "Failed to delete document chunks",
                collection=collection_name,
                document_source=document_source,
                error=str(e),
            )
            raise

        return deleted

    async def delete_source_chunks(
        self, collection_name: str, source_id: str
    ) -> int:
        """
        Delete all chunks from a specific knowledge source.

        Used when removing a source from a knowledge base so that only that
        source's documents are erased — other sources' chunks remain intact.

        Args:
            collection_name: The Qdrant collection.
            source_id: The ``source_id`` payload value (KnowledgeSource.id).

        Returns:
            Number of chunks deleted (best-effort from scroll count).
        """
        deleted = await self.count_source_chunks(collection_name, source_id)

        try:
            self.client.delete(
                collection_name=collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source_id",
                            match=MatchValue(value=source_id),
                        )
                    ]
                ),
            )
            logger.info(
                "Deleted source chunks",
                collection=collection_name,
                source_id=source_id,
                count=deleted,
            )
        except Exception as e:
            logger.error(
                "Failed to delete source chunks",
                collection=collection_name,
                source_id=source_id,
                error=str(e),
            )
            raise

        return deleted

    # ------------------------------------------------------------------
    # Count helpers
    # ------------------------------------------------------------------

    async def count_document_chunks(
        self, collection_name: str, document_source: str
    ) -> int:
        """
        Count chunks for a specific document.

        Args:
            collection_name: The Qdrant collection.
            document_source: The ``source`` payload value for the document.

        Returns:
            Number of matching chunks (0 if collection or document not found).
        """
        try:
            result = self.client.count(
                collection_name=collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="source",
                            match=MatchValue(value=document_source),
                        )
                    ]
                ),
                exact=False,  # Approximate is fine for reporting
            )
            return result.count
        except Exception as e:
            logger.warning(
                "Could not count document chunks",
                collection=collection_name,
                document_source=document_source,
                error=str(e),
            )
            return 0

    async def count_source_chunks(
        self, collection_name: str, source_id: str
    ) -> int:
        """
        Count all chunks from a specific knowledge source.

        Args:
            collection_name: The Qdrant collection.
            source_id: The ``source_id`` payload value (KnowledgeSource.id).

        Returns:
            Number of matching chunks (0 if not found).
        """
        try:
            result = self.client.count(
                collection_name=collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="source_id",
                            match=MatchValue(value=source_id),
                        )
                    ]
                ),
                exact=False,
            )
            return result.count
        except Exception as e:
            logger.warning(
                "Could not count source chunks",
                collection=collection_name,
                source_id=source_id,
                error=str(e),
            )
            return 0

    # ------------------------------------------------------------------
    # Metadata retrieval
    # ------------------------------------------------------------------

    async def get_document_metadata(
        self, collection_name: str, document_source: str
    ) -> dict:
        """
        Get metadata from the first chunk of a document.

        Returns payload fields such as ``title``, ``embedding_model``,
        ``scraped_at``, and the nested ``metadata`` dict (file_type, etc.).

        Args:
            collection_name: The Qdrant collection.
            document_source: The ``source`` payload value for the document.

        Returns:
            Dict of metadata, or empty dict if no chunks found.
        """
        try:
            points, _ = self.client.scroll(
                collection_name=collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="source",
                            match=MatchValue(value=document_source),
                        )
                    ]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )
            if not points:
                return {}
            payload = points[0].payload or {}
            return {
                "title": payload.get("title", ""),
                "source": payload.get("source", ""),
                "source_id": payload.get("source_id", ""),
                "embedding_model": payload.get("embedding_model", ""),
                "scraped_at": payload.get("scraped_at", ""),
                "content_hash": payload.get("content_hash", ""),
                "metadata": payload.get("metadata", {}),
            }
        except Exception as e:
            logger.warning(
                "Could not get document metadata",
                collection=collection_name,
                document_source=document_source,
                error=str(e),
            )
            return {}

    # ------------------------------------------------------------------
    # Full-text reconstruction from Qdrant (fallback)
    # ------------------------------------------------------------------

    async def get_document_text_from_qdrant(
        self, collection_name: str, document_source: str
    ) -> str:
        """
        Reconstruct document text by concatenating all chunks in order.

        This is a lossy fallback — chunk overlap means the reconstructed text
        will have repeated sentences.  Use Postgres ``ScrapedContent.raw_content``
        as the primary source for fidelity.

        Args:
            collection_name: The Qdrant collection.
            document_source: The ``source`` payload value.

        Returns:
            Concatenated chunk text, sorted by ``chunk_index``.
        """
        all_chunks: list[tuple[int, str]] = []
        offset = None

        try:
            while True:
                points, next_offset = self.client.scroll(
                    collection_name=collection_name,
                    scroll_filter=Filter(
                        must=[
                            FieldCondition(
                                key="source",
                                match=MatchValue(value=document_source),
                            )
                        ]
                    ),
                    limit=200,
                    offset=offset,
                    with_payload=True,
                    with_vectors=False,
                )

                for point in points:
                    payload = point.payload or {}
                    chunk_index = payload.get("chunk_index", 0)
                    content = payload.get("content", "")
                    all_chunks.append((chunk_index, content))

                if not next_offset:
                    break
                offset = next_offset

        except Exception as e:
            logger.error(
                "Failed to scroll document chunks from Qdrant",
                collection=collection_name,
                document_source=document_source,
                error=str(e),
            )
            return ""

        if not all_chunks:
            return ""

        all_chunks.sort(key=lambda x: x[0])
        return "\n\n".join(text for _, text in all_chunks)
