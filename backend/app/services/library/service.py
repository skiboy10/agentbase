"""
Knowledge Base Service

Manages Library and Document entities, including Qdrant collection
lifecycle for knowledge bases.

Two service classes:
- LibraryService: KB CRUD, source association, stats recalculation
- DocumentService: Document CRUD, search by title/content
"""
import re
import uuid
import hashlib
from datetime import datetime
from typing import Optional
from sqlalchemy import select, func, and_, or_, delete
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import get_settings
from app.models import Library, Document, Source, AgentLibrary, LibrarySource
from app.services.ingestion.embedding_processor import EmbeddingProcessor

settings = get_settings()
logger = structlog.get_logger()


class EmbeddingMismatchError(Exception):
    """Raised when a source's embedding model does not match a library's.

    Carries structured info so API layers and MCP tools can surface the
    full mismatch detail to external agents for programmatic adaptation.
    """

    def __init__(
        self,
        library_id: str,
        library_embedding_provider: Optional[str],
        library_embedding_model: Optional[str],
        source_id: str,
        source_embedding_provider: Optional[str],
        source_embedding_model: Optional[str],
    ):
        self.library_id = library_id
        self.library_embedding_provider = library_embedding_provider
        self.library_embedding_model = library_embedding_model
        self.source_id = source_id
        self.source_embedding_provider = source_embedding_provider
        self.source_embedding_model = source_embedding_model
        super().__init__(
            f"Source embedding {source_embedding_provider}/{source_embedding_model} "
            f"does not match library embedding {library_embedding_provider}/{library_embedding_model}"
        )

    def to_dict(self) -> dict:
        """Machine-readable payload for API/MCP error responses."""
        lib_model = f"{self.library_embedding_provider}/{self.library_embedding_model}"
        return {
            "error_code": "EMBEDDING_MISMATCH",
            "detail": (
                f"Source embedding model ({self.source_embedding_provider}/"
                f"{self.source_embedding_model}) does not match library embedding "
                f"model ({lib_model}). A library locks its embedding model to the "
                f"first source bound to it; all subsequent sources must match."
            ),
            "library": {
                "id": self.library_id,
                "embedding_provider": self.library_embedding_provider,
                "embedding_model": self.library_embedding_model,
            },
            "source": {
                "id": self.source_id,
                "embedding_provider": self.source_embedding_provider,
                "embedding_model": self.source_embedding_model,
            },
            "suggested_action": (
                f"Create a new source configured with embedding model '{lib_model}' "
                f"and bind that to this library, OR bind this source to a library whose "
                f"embedding model matches '{self.source_embedding_provider}/"
                f"{self.source_embedding_model}'."
            ),
        }


def _slugify_collection_name(name: str, kb_id: str) -> str:
    """
    Generate a safe Qdrant collection name from a KB name and its ID.

    Format: agentbase_kb_{slug}_{id_prefix}
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    slug = re.sub(r"_+", "_", slug)[:40]
    prefix = settings.qdrant_collection_prefix or "agentbase_"
    return f"{prefix}kb_{slug}_{kb_id[:8]}"


# ============================================================
# LibraryService
# ============================================================

class LibraryService:
    """
    Manages Library lifecycle including Qdrant collection creation/deletion
    and source-to-KB association.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._processor: Optional[EmbeddingProcessor] = None

    def _get_processor(self) -> EmbeddingProcessor:
        """Lazy-init embedding processor (avoids Qdrant connection at import time)."""
        if self._processor is None:
            self._processor = EmbeddingProcessor()
        return self._processor

    # ----------------------------------------------------------
    # Create
    # ----------------------------------------------------------

    async def create_kb(
        self,
        name: str,
        embedding_provider: Optional[str] = None,
        embedding_model: Optional[str] = None,
        description: Optional[str] = None,
        project_id: Optional[str] = None,
        taxonomy_id: Optional[str] = None,
        enrichment_model: Optional[str] = None,
        embedding_dimensions: Optional[int] = None,
        source_ids: Optional[list[str]] = None,
    ) -> Library:
        """
        Create a new Library and its backing Qdrant collection.

        The collection name is derived from the KB name + a UUID prefix so it
        is both human-readable and collision-safe.

        The DB row is flushed (not committed) so the PK is assigned within the
        current transaction.  The get_db() dependency handles the final
        commit/rollback — if anything fails, the entire transaction rolls back
        and no orphan rows are left behind.

        If *source_ids* is provided, the listed Sources are linked to
        the new KB atomically within the same transaction.
        """
        # Uniqueness guard — prevent duplicate KB names
        existing = await self.db.execute(
            select(Library).where(Library.name == name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Library '{name}' already exists")

        kb_id = str(uuid.uuid4())
        collection_name = _slugify_collection_name(name, kb_id)

        kb = Library(
            id=kb_id,
            name=name,
            description=description,
            project_id=project_id,
            collection_name=collection_name,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dimensions=embedding_dimensions,
            taxonomy_id=taxonomy_id,
            enrichment_model=enrichment_model,
        )
        self.db.add(kb)
        await self.db.flush()
        await self.db.refresh(kb)

        # Create Qdrant collection — requires knowing the vector size.
        # We use embedding_dimensions if provided, otherwise defer creation to first
        # indexing run (the indexer will call create_collection when it has a real size).
        if embedding_dimensions:
            try:
                processor = self._get_processor()
                if not processor.collection_exists(collection_name):
                    processor.create_collection(collection_name, embedding_dimensions)
                    logger.info(
                        "Created Qdrant collection for knowledge base",
                        collection=collection_name,
                        kb_id=kb_id,
                    )
            except Exception as exc:
                logger.warning(
                    "Could not create Qdrant collection during KB creation — will be created on first index",
                    collection=collection_name,
                    error=str(exc),
                    exc_info=True,
                )

        # Atomic source linking — bind requested sources within the same txn.
        # Reuses the same embedding-lock rules as add_source to enforce consistency.
        if source_ids:
            for sid in source_ids:
                stmt = select(Source).where(Source.id == sid)
                result = await self.db.execute(stmt)
                source = result.scalar_one_or_none()
                if source is None:
                    raise ValueError(f"Source '{sid}' not found")
                self._validate_and_lock_embedding(kb, source)
                self.db.add(LibrarySource(library_id=kb_id, source_id=sid))

            # Update denormalised stats from the newly linked sources
            stats = await self._compute_kb_stats(kb_id)
            kb.source_count, kb.document_count, kb.chunk_count = stats

        await self.db.commit()
        logger.info("Created knowledge base", kb_id=kb_id, name=name)
        # Re-fetch with selectinload(sources) to avoid lazy-load greenlet
        # crash when the caller accesses kb.sources for serialization.
        return await self.get_kb(kb_id)

    # ----------------------------------------------------------
    # Read
    # ----------------------------------------------------------

    async def get_kb(self, kb_id: str) -> Optional[Library]:
        """Fetch a KB with eagerly loaded sources."""
        stmt = (
            select(Library)
            .options(selectinload(Library.sources))
            .where(Library.id == kb_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_kbs(self, project_id: Optional[str] = None) -> list[Library]:
        """List KBs, optionally filtered by project."""
        stmt = select(Library).options(selectinload(Library.sources))
        if project_id is not None:
            stmt = stmt.where(Library.project_id == project_id)
        stmt = stmt.order_by(Library.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ----------------------------------------------------------
    # Update
    # ----------------------------------------------------------

    async def update_kb(self, kb_id: str, **kwargs) -> Optional[Library]:
        """Update KB metadata fields (name, description, taxonomy_id, enrichment_model)."""
        kb = await self.get_kb(kb_id)
        if kb is None:
            return None

        allowed_fields = {"name", "description", "taxonomy_id", "enrichment_model", "status"}
        for field, value in kwargs.items():
            if field in allowed_fields:
                setattr(kb, field, value)

        kb.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(kb)
        logger.info("Updated knowledge base", kb_id=kb_id, fields=list(kwargs.keys()))
        return kb

    # ----------------------------------------------------------
    # Delete
    # ----------------------------------------------------------

    async def delete_kb(self, kb_id: str) -> bool:
        """
        Delete a KB, its Qdrant collection, and all Document records.

        Documents are cascade-deleted by the DB; chunks in Qdrant are removed
        by deleting the collection itself.
        """
        kb = await self.get_kb(kb_id)
        if kb is None:
            return False

        collection_name = kb.collection_name

        # Sources have knowledge_base_id FK with ON DELETE SET NULL, so the
        # DB will automatically disassociate them when the KB row is deleted.
        await self.db.delete(kb)
        await self.db.commit()

        # Delete Qdrant collection after DB commit
        try:
            processor = self._get_processor()
            processor.delete_collection(collection_name)
            logger.info("Deleted Qdrant collection", collection=collection_name)
        except Exception as exc:
            logger.warning("Failed to delete Qdrant collection", collection=collection_name, error=str(exc))

        logger.info("Deleted knowledge base", kb_id=kb_id)
        return True

    # ----------------------------------------------------------
    # Source management
    # ----------------------------------------------------------

    async def add_source(self, kb_id: str, source_id: str) -> Optional[dict]:
        """Associate an existing Source with this KB via the junction table.

        Enforces embedding-model compatibility:
          - If the library has no embedding model yet (newly created, empty),
            the source's embedding model locks in as the library's model.
          - Otherwise the source must match, or EmbeddingMismatchError is raised.

        If the source is already indexed, a re-index job is enqueued so the
        new library's Qdrant collection gets populated (the indexer fans out
        to all libraries a source belongs to).

        Returns a dict describing the binding result, or None if the library
        or source doesn't exist. Idempotent — a pre-existing binding returns
        ``{"bound": True, "already_bound": True, "reindex_queued": False}``.
        """
        # Lock the library row to serialize concurrent add_source calls
        # against the "first source locks embedding" invariant.
        lock_stmt = select(Library).where(Library.id == kb_id).with_for_update()
        lock_result = await self.db.execute(lock_stmt)
        kb_locked = lock_result.scalar_one_or_none()
        if kb_locked is None:
            return None

        # Reload with source relationship for downstream use
        kb = await self.get_kb(kb_id)
        if kb is None:
            return None

        stmt = select(Source).where(Source.id == source_id)
        result = await self.db.execute(stmt)
        source = result.scalar_one_or_none()
        if source is None:
            return None

        # Idempotency: if already bound, do nothing
        existing = await self.db.execute(
            select(LibrarySource).where(
                and_(
                    LibrarySource.library_id == kb_id,
                    LibrarySource.source_id == source_id,
                )
            )
        )
        if existing.scalar_one_or_none() is not None:
            return {"bound": True, "already_bound": True, "reindex_queued": False}

        # Validate embedding compatibility and lock library's model if empty
        self._validate_and_lock_embedding(kb, source)

        self.db.add(LibrarySource(library_id=kb_id, source_id=source_id))

        # If the source is already indexed, its chunks live only in the
        # libraries it was indexed into. Enqueue a re-index so the new
        # library's collection gets populated via the indexer's fan-out.
        reindex_queued = False
        if source.status == "indexed":
            from app.services.job_service import JobService
            from app.models import Job

            existing_job = await self.db.execute(
                select(Job).where(
                    and_(
                        Job.job_type == "index_source",
                        Job.status.in_(["queued", "running"]),
                        Job.payload["source_id"].as_string() == source_id,
                    )
                )
            )
            if existing_job.scalar_one_or_none() is None:
                job_svc = JobService(self.db)
                await job_svc.enqueue(
                    job_type="index_source",
                    payload={"source_id": source_id, "reason": "library_bind", "library_id": kb_id},
                    priority=1,
                )
                reindex_queued = True

        await self.db.commit()
        await self.recalculate_stats(kb_id)
        logger.info(
            "Added source to knowledge base",
            kb_id=kb_id,
            source_id=source_id,
            reindex_queued=reindex_queued,
        )
        return {"bound": True, "already_bound": False, "reindex_queued": reindex_queued}

    async def remove_source(self, kb_id: str, source_id: str) -> bool:
        """
        Remove a source from a KB.

        Deletes the junction row and all Document records for that source
        within the KB. Callers are responsible for removing corresponding
        Qdrant chunks if needed.
        """
        result = await self.db.execute(
            select(LibrarySource).where(
                and_(
                    LibrarySource.library_id == kb_id,
                    LibrarySource.source_id == source_id,
                )
            )
        )
        binding = result.scalar_one_or_none()
        if binding is None:
            return False

        await self.db.delete(binding)

        # Delete Document records for this source in this KB
        del_stmt = delete(Document).where(
            and_(Document.source_id == source_id, Document.library_id == kb_id)
        )
        await self.db.execute(del_stmt)
        await self.db.commit()
        await self.recalculate_stats(kb_id)
        logger.info("Removed source from knowledge base", kb_id=kb_id, source_id=source_id)
        return True

    # ----------------------------------------------------------
    # Embedding lock
    # ----------------------------------------------------------

    def _validate_and_lock_embedding(self, kb: Library, source: Source) -> None:
        """Validate source embedding matches library; lock library if empty.

        Called during source-to-library binding. If the library has no embedding
        model set yet (newly created, no sources), the source's embedding model
        is set on the library. Otherwise the source must match exactly.

        Raises EmbeddingMismatchError if the source has an embedding model and
        it doesn't match the library's.
        """
        source_provider = source.embedding_provider
        source_model = source.embedding_model

        # If library has no embedding set yet, lock in the source's model.
        if not kb.embedding_provider or not kb.embedding_model:
            if source_provider and source_model:
                kb.embedding_provider = source_provider
                kb.embedding_model = source_model
                kb.embedding_dimensions = source.embedding_dimensions
                logger.info(
                    "Library embedding model locked by first source",
                    kb_id=kb.id,
                    source_id=source.id,
                    provider=source_provider,
                    model=source_model,
                )
            return

        # Library already has an embedding model — source must match.
        # A source with no explicit embedding config inherits the library's,
        # so that case is treated as a match.
        if source_provider and source_model:
            # If library has provider+model set but no dims (created via API with
            # explicit provider/model but caller omitted dims), backfill from source.
            # Without this, the indexer falls back to 1536 and Qdrant collection
            # is created with the wrong vector size, causing dimension errors on index.
            if kb.embedding_dimensions is None and source.embedding_dimensions is not None:
                kb.embedding_dimensions = source.embedding_dimensions
                logger.info(
                    "Library embedding_dimensions backfilled from source",
                    kb_id=kb.id,
                    source_id=source.id,
                    dimensions=source.embedding_dimensions,
                )

            # Treat a None library dim as a mismatch when the source has a known dim —
            # this prevents the silent-acceptance path that leads to wrong-size collections.
            dims_mismatch = source.embedding_dimensions is not None and (
                kb.embedding_dimensions is None
                or source.embedding_dimensions != kb.embedding_dimensions
            )
            if (
                source_provider != kb.embedding_provider
                or source_model != kb.embedding_model
                or dims_mismatch
            ):
                raise EmbeddingMismatchError(
                    library_id=kb.id,
                    library_embedding_provider=kb.embedding_provider,
                    library_embedding_model=kb.embedding_model,
                    source_id=source.id,
                    source_embedding_provider=source_provider,
                    source_embedding_model=source_model,
                )

    # ----------------------------------------------------------
    # Stats
    # ----------------------------------------------------------

    async def _compute_kb_stats(self, kb_id: str) -> tuple[int, int, int]:
        """Return (source_count, document_count, chunk_count) for a KB.

        - ``source_count``: number of Sources bound via library_sources.
        - ``document_count``: rows in ``documents`` table for this library
          (the same set the Documents tab renders).
        - ``chunk_count``: sum of ``Document.chunk_count`` rows in this library.

        Document/chunk counts come from the ``documents`` table rather than
        ``Source.document_count`` / ``Source.chunk_count`` so the card always
        agrees with the Documents tab.
        """
        # source_count via the junction
        src_result = await self.db.execute(
            select(func.count(Source.id))
            .select_from(LibrarySource)
            .join(Source, Source.id == LibrarySource.source_id)
            .where(LibrarySource.library_id == kb_id)
        )
        src_count = src_result.scalar() or 0

        # document/chunk counts from the documents table
        doc_result = await self.db.execute(
            select(
                func.count(Document.id),
                func.coalesce(func.sum(Document.chunk_count), 0),
            ).where(Document.library_id == kb_id)
        )
        doc_count, chunk_count = doc_result.one()
        return int(src_count or 0), int(doc_count or 0), int(chunk_count or 0)

    async def recalculate_stats(self, kb_id: str) -> Optional[Library]:
        """Recount sources, documents, and chunks for a KB.

        Document and chunk counts are aggregated from the constituent
        Sources' own denormalised stats via the library_sources junction.
        """
        kb = await self.get_kb(kb_id)
        if kb is None:
            return None

        src_count, doc_count, chunk_count = await self._compute_kb_stats(kb_id)
        kb.source_count = src_count
        kb.document_count = doc_count
        kb.chunk_count = chunk_count
        kb.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(kb)
        logger.info(
            "Recalculated KB stats",
            kb_id=kb_id,
            sources=kb.source_count,
            documents=kb.document_count,
            chunks=kb.chunk_count,
        )
        return kb


# ============================================================
# DocumentService
# ============================================================

class DocumentService:
    """
    Manages Document records within a Library.

    Documents track the full text and chunk metadata for each piece of content
    ingested into a KB. The actual vector chunks live in Qdrant; this service
    manages the relational records.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ----------------------------------------------------------
    # Create / Update
    # ----------------------------------------------------------

    async def create_document(
        self,
        kb_id: str,
        source_id: str,
        document_id: str,
        title: Optional[str] = None,
        full_text: Optional[str] = None,
        file_path: Optional[str] = None,
        url: Optional[str] = None,
        file_type: Optional[str] = None,
        document_type: Optional[str] = None,
        chunk_count: int = 0,
        status: str = "pending",
    ) -> Document:
        """Create a new Document record."""
        content_hash = None
        text_length = 0
        if full_text:
            content_hash = hashlib.sha256(full_text.encode()).hexdigest()
            text_length = len(full_text)

        doc = Document(
            library_id=kb_id,
            source_id=source_id,
            document_id=document_id,
            title=title,
            full_text=full_text,
            text_length=text_length,
            content_hash=content_hash,
            file_path=file_path,
            url=url,
            file_type=file_type,
            document_type=document_type,
            chunk_count=chunk_count,
            status=status,
        )
        self.db.add(doc)
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    async def update_document(self, doc_id: str, **kwargs) -> Optional[Document]:
        """Update document metadata or status."""
        doc = await self.get_document(doc_id)
        if doc is None:
            return None

        allowed_fields = {
            "title", "full_text", "file_path", "url", "file_type",
            "document_type", "chunk_count", "status", "error_message",
            "indexed_at", "classification", "classification_taxonomy_version",
        }
        for field, value in kwargs.items():
            if field in allowed_fields:
                setattr(doc, field, value)

        # Recompute hash and length if full_text was updated
        if "full_text" in kwargs and kwargs["full_text"]:
            doc.content_hash = hashlib.sha256(kwargs["full_text"].encode()).hexdigest()
            doc.text_length = len(kwargs["full_text"])

        doc.updated_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(doc)
        return doc

    # ----------------------------------------------------------
    # Read
    # ----------------------------------------------------------

    async def get_document(self, doc_id: str) -> Optional[Document]:
        """Get a document by its primary key (includes full_text and source)."""
        stmt = (
            select(Document)
            .options(selectinload(Document.source))
            .where(Document.id == doc_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_document_text(self, doc_id: str) -> Optional[str]:
        """Return just the full_text of a document (lightweight retrieval)."""
        doc = await self.get_document(doc_id)
        return doc.full_text if doc else None

    async def list_documents(
        self,
        kb_id: str,
        source_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        file_type: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> list[Document]:
        """Paginated list of documents for a KB, optionally filtered.

        Filters:
            source_id: restrict to a specific source binding
            file_type: filter by ``Document.file_type`` (e.g. 'pdf', 'url')
            document_type: filter by ``Document.document_type``

        ``Document.source`` is eagerly loaded so callers can access
        ``doc.source.name`` without triggering a lazy load in async code.
        """
        stmt = (
            select(Document)
            .options(selectinload(Document.source))
            .where(Document.library_id == kb_id)
        )
        if source_id:
            stmt = stmt.where(Document.source_id == source_id)
        if file_type:
            stmt = stmt.where(Document.file_type == file_type)
        if document_type:
            stmt = stmt.where(Document.document_type == document_type)
        stmt = stmt.order_by(Document.created_at.desc()).limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def count_documents(
        self,
        kb_id: str,
        source_id: Optional[str] = None,
        file_type: Optional[str] = None,
        document_type: Optional[str] = None,
    ) -> int:
        """Count total documents for a KB matching the same filters as list_documents."""
        stmt = select(func.count(Document.id)).where(Document.library_id == kb_id)
        if source_id:
            stmt = stmt.where(Document.source_id == source_id)
        if file_type:
            stmt = stmt.where(Document.file_type == file_type)
        if document_type:
            stmt = stmt.where(Document.document_type == document_type)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def search_documents(self, kb_id: str, query: str) -> list[Document]:
        """
        Simple full-text search over document title and content.

        Uses SQL ILIKE for case-insensitive substring matching. For production
        full-text search use the Qdrant-backed RAG pipeline instead.
        """
        pattern = f"%{query}%"
        stmt = (
            select(Document)
            .options(selectinload(Document.source))
            .where(Document.library_id == kb_id)
            .where(
                or_(
                    Document.title.ilike(pattern),
                    Document.full_text.ilike(pattern),
                )
            )
            .order_by(Document.created_at.desc())
            .limit(50)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # ----------------------------------------------------------
    # Delete
    # ----------------------------------------------------------

    async def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document record.

        Note: Qdrant chunk cleanup (deleting vectors with matching doc_id payload)
        is the caller's responsibility — this service only manages the relational record.
        """
        doc = await self.get_document(doc_id)
        if doc is None:
            return False
        await self.db.delete(doc)
        await self.db.commit()
        return True

    async def get_document_by_document_id(
        self, kb_id: str, document_id: str
    ) -> Optional[Document]:
        """Get a document by its stable document_id within a KB."""
        stmt = select(Document).where(
            Document.library_id == kb_id,
            Document.document_id == document_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_document(
        self,
        library_id: str,
        source_id: str,
        document_id: str,
        title: str,
        full_text: str,
        content_hash: str,
        file_path: Optional[str] = None,
        file_type: Optional[str] = None,
        url: Optional[str] = None,
        classification: Optional[dict] = None,
        document_type: Optional[str] = None,
        chunk_count: int = 0,
    ) -> Document:
        """Create or update a Document record."""
        existing = await self.get_document_by_document_id(library_id, document_id)
        if existing:
            existing.title = title
            existing.full_text = full_text
            existing.text_length = len(full_text) if full_text else 0
            existing.content_hash = content_hash
            existing.file_path = file_path
            existing.file_type = file_type
            existing.classification = classification
            existing.document_type = document_type
            existing.chunk_count = chunk_count
            existing.status = "indexed"
            existing.indexed_at = datetime.utcnow()
            existing.error_message = None
            await self.db.flush()
            return existing
        else:
            doc = Document(
                library_id=library_id,
                source_id=source_id,
                document_id=document_id,
                title=title,
                file_path=file_path,
                url=url,
                file_type=file_type,
                full_text=full_text,
                text_length=len(full_text) if full_text else 0,
                content_hash=content_hash,
                classification=classification,
                document_type=document_type,
                chunk_count=chunk_count,
                status="indexed",
                indexed_at=datetime.utcnow(),
            )
            self.db.add(doc)
            await self.db.flush()
            return doc
