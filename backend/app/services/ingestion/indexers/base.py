"""
Base indexer with shared embedding and batch processing logic.

All indexers inherit from this class to share common functionality.
"""
import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import structlog

from app.core.config import get_settings
from app.models import Source, ModelAssignment, ScrapedContent, Library, LibrarySource
from app.providers.embedding_registry import get_embedding_registry

from ..qdrant_client import get_qdrant_client

settings = get_settings()
logger = structlog.get_logger()


class BaseIndexer:
    """
    Base class for all indexers.

    Provides common functionality for:
    - Embedding configuration retrieval
    - Batch embedding processing
    - Qdrant collection management
    - Content hashing for change detection
    """

    # Default batch size for embedding operations
    BATCH_SIZE = 50

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client: QdrantClient = get_qdrant_client()
        self.embedding_registry = get_embedding_registry()
        self._source_default_metadata: Optional[dict] = None
        # Cache of libraries loaded per source (multi-library support)
        self._kbs_cache: dict[str, list] = {}

    # ------------------------------------------------------------------ #
    # Progress publishing
    # ------------------------------------------------------------------ #

    async def _publish_progress(self) -> None:
        """Commit the main session to make pending progress writes visible.

        The indexer's session holds a long-running transaction (chunks,
        IndexingLog updates, document_content rows, progress field updates).
        PostgreSQL's default READ COMMITTED isolation means those writes are
        invisible to other connections until the transaction commits — so the
        API status endpoint stays stuck at "Starting indexing..." for the
        entire duration even though work is happening.

        We can't UPDATE the source row from a side session: the main session
        already holds a row-level write lock on it (from prior ``flush()``
        calls touching progress fields), so any side-session UPDATE would
        deadlock until the main run finishes.

        Instead we commit the main session, which releases all locks and
        makes prior writes visible. The next statement on the same session
        starts a fresh transaction automatically. Callers should only invoke
        this at safe checkpoints — i.e., between fully-processed work units,
        not mid-batch — since rollback after this point can't undo the
        committed work.

        Failures here are swallowed: observability must not break indexing.
        """
        try:
            await self.db.commit()
        except Exception as e:
            logger.warning("Failed to publish progress checkpoint", error=str(e))

    # ------------------------------------------------------------------ #
    # Knowledge Base helpers
    # ------------------------------------------------------------------ #

    async def _load_kb_for_source(self, source: "Source") -> None:
        """Load all Libraries a source belongs to (via library_sources junction).

        All libraries sharing a source must have matching embedding models
        (enforced by LibraryService on add), so any of them is safe for
        embedding config. Ordered by binding creation time so the earliest
        binding is treated as "primary".
        """
        stmt = (
            select(Library)
            .join(LibrarySource, LibrarySource.library_id == Library.id)
            .where(LibrarySource.source_id == source.id)
            .order_by(LibrarySource.created_at.asc())
        )
        result = await self.db.execute(stmt)
        kbs = list(result.scalars().all())
        self._kbs_cache[source.id] = kbs

    def _get_kbs(self, source: "Source") -> list:
        """Return the list of Libraries a source belongs to (may be empty)."""
        return self._kbs_cache.get(source.id, [])

    def _get_kb(self, source: "Source"):
        """Return the primary (earliest-bound) Library for a source, or None."""
        kbs = self._get_kbs(source)
        return kbs[0] if kbs else None

    def _get_collections_for_source(self, source: "Source") -> list[str]:
        """Return every Qdrant collection that holds this source's chunks.

        The source's own collection always holds the primary copy the read path
        queries; each bound library's collection holds a mirror. Returns the
        source's own collection alone when it is unbound.
        """
        return [
            source.collection_name,
            *(kb.collection_name for kb in self._get_kbs(source)),
        ]

    def _get_collection_for_source(self, source: "Source") -> str:
        """Return the source's own collection — the primary write/read target.

        The search, chat and coverage read paths all resolve a source's chunks
        via ``Source.collection_name``, so that collection MUST be where the
        searchable copy of every chunk lives — including for library-bound
        sources. Library collections receive *mirror* copies via
        :meth:`_get_library_mirror_collections`; they are never the primary,
        otherwise post-binding chunks would be invisible to search.
        """
        return source.collection_name

    def _get_library_mirror_collections(
        self, source: "Source"
    ) -> list[tuple[str, str]]:
        """Return ``(collection_name, library_id)`` for every bound library.

        Chunks are mirrored into each bound library's collection so those
        collections stay populated, but the source's own collection (see
        :meth:`_get_collection_for_source`) remains the primary searchable home.
        Empty for an unbound source.
        """
        return [(kb.collection_name, kb.id) for kb in self._get_kbs(source)]

    def _get_embedding_for_source(self, source: "Source") -> Optional[tuple]:
        """Return (provider, model, dims) from the primary library, else None.

        All libraries bound to a source share the same embedding model by
        contract (enforced at add-source time), so the primary is sufficient.
        """
        kb = self._get_kb(source)
        if kb and kb.embedding_provider and kb.embedding_model:
            return kb.embedding_provider, kb.embedding_model, kb.embedding_dimensions or 1536
        return None

    @staticmethod
    def _generate_document_id(source_id: str, locator: str) -> str:
        """Generate a stable document_id: {source_id[:8]}:{sha256(locator)[:16]}.

        ``locator`` is the URL, file path, or any stable identifier that is
        unique within the source. The same (source_id, locator) pair always
        produces the same document_id so re-indexing upserts cleanly.
        """
        path_hash = hashlib.sha256(locator.encode()).hexdigest()[:16]
        return f"{source_id[:8]}:{path_hash}"

    async def _upsert_kb_documents(
        self,
        source: "Source",
        kbs: list,
        document_id: str,
        title: Optional[str],
        full_text: Optional[str],
        content_hash: Optional[str],
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        file_type: Optional[str] = None,
        document_type: Optional[str] = "standard",
        classification: Optional[dict] = None,
        chunk_count: int = 0,
    ) -> None:
        """Create/update a Document row in every Library bound to this source.

        No-op when ``kbs`` is empty (legacy non-library indexing path).

        Reuses :meth:`DocumentService.upsert_document` for the create-or-update
        logic. Imported lazily to avoid circular imports between the ingestion
        and library service packages.
        """
        if not kbs:
            return
        from app.services.library import DocumentService

        doc_service = DocumentService(self.db)
        for kb in kbs:
            await doc_service.upsert_document(
                library_id=kb.id,
                source_id=source.id,
                document_id=document_id,
                title=title or "",
                file_path=file_path,
                url=url,
                file_type=file_type,
                full_text=full_text or "",
                content_hash=content_hash or "",
                classification=classification,
                document_type=document_type,
                chunk_count=chunk_count,
            )

    async def _ensure_collection_exists(self, collection_name: str, vector_size: int) -> None:
        """Create collection if it doesn't exist. Never destroys existing data."""
        try:
            self.client.get_collection(collection_name)
        except Exception:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    def _load_source_metadata(self, source: "Source") -> None:
        """Load structured metadata from a knowledge source for injection into Qdrant payloads."""
        self._source_default_metadata = source.default_metadata if source.default_metadata else None

    def _generate_collection_name(self, source_id: str) -> str:
        """Generate a Qdrant collection name for a knowledge source."""
        return f"{settings.qdrant_collection_prefix}{source_id}"

    async def _get_embedding_config(
        self, source: Optional["Source"] = None
    ) -> tuple[str, str, int]:
        """Get the embedding configuration to use for indexing.

        Precedence:
        1. Library-level config (if source is bound to one — all bound
           libraries share the same model by contract)
        2. Source-level config (``source.embedding_provider`` /
           ``source.embedding_model``)
        3. Global default from ``ModelAssignment``
        4. App settings fallback
        """
        if source is not None:
            kb_config = self._get_embedding_for_source(source)
            if kb_config:
                return kb_config
            if source.embedding_provider and source.embedding_model:
                provider = self.embedding_registry.get_provider(source.embedding_provider)
                dimensions = (
                    source.embedding_dimensions
                    or (provider.get_model_dimensions(source.embedding_model) if provider else 1536)
                )
                return source.embedding_provider, source.embedding_model, dimensions

        stmt = select(ModelAssignment).where(
            ModelAssignment.task_type == "embedding",
            ModelAssignment.project_id.is_(None)
        )
        result = await self.db.execute(stmt)
        assignment = result.scalars().first()

        if assignment:
            provider = self.embedding_registry.get_provider(assignment.provider)
            dimensions = provider.get_model_dimensions(assignment.model) if provider else 1536
            return assignment.provider, assignment.model, dimensions

        return (
            settings.embedding_provider,
            settings.embedding_model,
            1536
        )

    def _compute_content_hash(self, content: str) -> str:
        """Compute SHA256 hash of content for change detection."""
        return hashlib.sha256(content.encode()).hexdigest()

    async def _process_embedding_batch(
        self,
        collection_name: str,
        chunks: list[str],
        metadata: list[dict],
        provider: str,
        model: str,
        default_metadata: Optional[dict] = None,
        mirror_targets: Optional[list[tuple[str, str]]] = None,
    ) -> tuple[int, int]:
        """Process a batch of chunks, generate embeddings, and upsert to Qdrant.

        Qdrant payload contract
        -----------------------
        Every point written to Qdrant MUST contain these fields so that
        SearchResult can populate its top-level citation fields:

            content       (str)  — The chunk text
            source        (str)  — Clean file path or URL (NOT a bare UUID)
            source_id     (str)  — UUID of the Source row
            chunk_index   (int)  — 0-based position of this chunk in the document
            title         (str)  — Human-readable title; falls back to filename
                                   when the indexer cannot determine a title
            embedding_model (str) — "{provider}/{model}" used at index time

        Callers that add document-level metadata (document_id, library_id)
        should include those keys in ``meta`` before calling this method.

        Args:
            default_metadata: Structured metadata from the knowledge source to merge
                             into each chunk's Qdrant payload for filtered search.
            mirror_targets: Optional list of ``(collection_name, library_id)`` pairs
                           to fan-out the same embeddings to. Used when a source is
                           bound to multiple libraries — embeddings are computed once
                           and written to each library's Qdrant collection with the
                           appropriate ``library_id`` payload override.

        Returns:
            Tuple of (points_count, dimensions) where dimensions is from the actual
            embedding response.
        """
        response = await self.embedding_registry.embed(provider, model, chunks)
        current_time = datetime.utcnow().isoformat()
        embedding_model_id = f"{provider}/{model}"

        points = []
        for embedding, chunk, meta in zip(response.embeddings, chunks, metadata):
            # Enforce title fallback: prefer explicit title, fall back to the
            # filename portion of the source path so the field is never empty.
            raw_source = meta["source"]
            title = meta.get("title") or ""
            if not title and raw_source:
                # Extract just the filename from the path as a last resort
                title = raw_source.rstrip("/").split("/")[-1]

            payload = {
                # Core content
                "content": chunk,
                "source": raw_source,
                "source_id": meta["source_id"],
                "chunk_index": meta["chunk_index"],
                "title": title,
                # Change detection and auditing
                "content_hash": self._compute_content_hash(chunk),
                "scraped_at": meta.get("scraped_at", current_time),
                "embedding_model": embedding_model_id,
                # Extensible metadata
                "metadata": meta.get("metadata", {}),
            }
            # folder_ancestors: every parent folder of this chunk's source file,
            # canonicalised. Populated by directory / file-item indexers so the
            # sub-source filter overlay can MatchAny on it. Other indexers
            # (URL, GitHub) leave it absent — they don't carry a folder concept.
            if meta.get("folder_ancestors"):
                payload["folder_ancestors"] = meta["folder_ancestors"]
            # KB-aware fields (added when source belongs to a Knowledge Base)
            if meta.get("document_id"):
                payload["document_id"] = meta["document_id"]
            if meta.get("library_id"):
                payload["library_id"] = meta["library_id"]
            # Merge structured metadata into root payload for Qdrant filtering
            # Use explicit None check so empty dict {} doesn't fall back
            effective_metadata = default_metadata if default_metadata is not None else self._source_default_metadata
            if effective_metadata:
                _reserved = {"content", "source", "source_id", "chunk_index", "title",
                             "content_hash", "scraped_at", "embedding_model", "metadata"}
                for key, value in effective_metadata.items():
                    if key not in _reserved:
                        payload[key] = value
            points.append(PointStruct(id=meta["id"], vector=embedding, payload=payload))

        self.client.upsert(collection_name=collection_name, points=points)

        # Fan-out to mirror collections (additional libraries a source belongs to).
        # Same embeddings, same payload except library_id is rewritten per target.
        if mirror_targets:
            for mirror_coll, mirror_lib_id in mirror_targets:
                mirror_points = []
                for p in points:
                    mirror_payload = dict(p.payload)
                    mirror_payload["library_id"] = mirror_lib_id
                    mirror_points.append(
                        PointStruct(id=p.id, vector=p.vector, payload=mirror_payload)
                    )
                self.client.upsert(collection_name=mirror_coll, points=mirror_points)
        return len(points), response.dimensions

    async def _setup_collection(
        self,
        collection_name: str,
        vector_size: int,
        recreate: bool = True
    ) -> None:
        """Create or recreate a Qdrant collection.

        Args:
            recreate: If True, delete and recreate. If False, create only if missing.
        """
        if recreate:
            try:
                self.client.delete_collection(collection_name)
            except Exception:
                pass
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )
        else:
            # Only create if it doesn't already exist
            try:
                self.client.get_collection(collection_name)
            except Exception:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )

    async def _store_embedding_config(
        self,
        source: Source,
        provider: str,
        model: str,
        dimensions: int
    ) -> None:
        """Store embedding configuration on the source for retrieval validation."""
        source.embedding_provider = provider
        source.embedding_model = model
        source.embedding_dimensions = dimensions
        await self.db.flush()

    async def _update_embedding_dimensions(
        self,
        source: Source,
        actual_dimensions: int
    ) -> None:
        """Update embedding dimensions from actual embedding response.

        Called after first embedding batch to correct any mismatch between
        hardcoded dimension lookups and actual model output.
        """
        if source.embedding_dimensions != actual_dimensions:
            logger.info(
                "Updating embedding dimensions from actual response",
                source_id=str(source.id),
                configured=source.embedding_dimensions,
                actual=actual_dimensions,
            )
            source.embedding_dimensions = actual_dimensions
            await self.db.flush()

    async def _update_progress(
        self,
        source: Source,
        progress: int,
        message: str
    ) -> None:
        """Update source progress fields."""
        source.progress = progress
        source.progress_message = message
        source.progress_updated_at = datetime.utcnow()
        await self.db.flush()

    async def _finalize_indexing(
        self,
        source: Source,
        doc_count: int,
        chunk_count: int,
        total_items: int,
        failed_count: int = 0,
        item_type: str = "documents"
    ) -> None:
        """Finalize indexing with success status and counts."""
        source.document_count = doc_count
        source.chunk_count = chunk_count
        source.last_indexed = datetime.utcnow()
        source.progress = total_items
        source.progress_updated_at = datetime.utcnow()

        # Silent-failure guards — surface two distinct zero-output conditions:
        #
        # 1. Total failure: all items failed to scrape (doc_count == 0 but
        #    items were attempted). Already visible via failed_count but the
        #    status was still "indexed" — confusing.
        #
        # 2. Hydration failure: scraper fetched pages (doc_count > 0) but
        #    the chunker produced nothing. Most common cause: JS content not
        #    rendered before extraction, or an anti-bot shell page.
        #
        # Both cases flip status to "error" so callers have a clear signal.
        if doc_count == 0 and total_items > 0:
            source.status = "error"
            source.error_message = (
                f"Failed to index any {item_type} — all {total_items} attempts failed. "
                "Check indexing logs for per-URL errors."
            )
            source.progress_message = f"Error: 0/{total_items} {item_type} succeeded"
            logger.warning(
                "Indexing failed: no documents produced",
                source_id=str(source.id),
                total_items=total_items,
                failed_count=failed_count,
            )
        elif doc_count > 0 and chunk_count == 0:
            source.status = "error"
            source.error_message = (
                "Scraped content produced no chunks — likely JS-rendered or anti-bot blocked. "
                "Try re-indexing; if it persists the site may require a different fetch strategy."
            )
            source.progress_message = f"Error: {doc_count} {item_type} scraped, 0 chunks produced"
            logger.warning(
                "Indexing produced zero chunks despite scraped pages",
                source_id=str(source.id),
                document_count=doc_count,
            )
        else:
            source.status = "indexed"
            source.error_message = None
            source.progress_message = f"Complete: {doc_count} {item_type}, {chunk_count} chunks"
            if failed_count > 0:
                source.progress_message += f" ({failed_count} failed)"

        # Recompute next_refresh_at for automatic freshness policy
        from app.services.freshness_service import compute_next_refresh_at
        source.next_refresh_at = compute_next_refresh_at(source)

        await self.db.flush()

    def _get_text_splitter(self):
        """Get a configured text splitter."""
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        return RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    async def _save_scraped_content(
        self,
        source: Source,
        url: str,
        title: str | None,
        content: str,
    ) -> ScrapedContent:
        """Save raw scraped content to postgres for re-embedding experiments.

        Uses upsert pattern: updates existing record if URL already scraped,
        creates new record otherwise.
        """
        from sqlalchemy import select

        content_hash = self._compute_content_hash(content)

        # Check for existing content
        stmt = select(ScrapedContent).where(
            ScrapedContent.source_id == source.id,
            ScrapedContent.url == url
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing record
            existing.title = title
            existing.raw_content = content
            existing.content_hash = content_hash
            existing.content_length = len(content)
            existing.scraped_at = datetime.utcnow()
            await self.db.flush()
            logger.debug("Updated scraped content", url=url, source_id=source.id)
            return existing
        else:
            # Create new record
            scraped = ScrapedContent(
                source_id=source.id,
                url=url,
                title=title,
                raw_content=content,
                content_hash=content_hash,
                content_length=len(content),
            )
            self.db.add(scraped)
            await self.db.flush()
            logger.debug("Saved scraped content", url=url, source_id=source.id)
            return scraped
