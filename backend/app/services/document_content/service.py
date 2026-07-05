"""
DocumentContent Service — manage raw document storage for re-embedding.

Handles web-scraped pages, uploaded files, and directory-sourced documents.
This is the successor to the implicit ScrapedContent operations scattered
across the ingestion indexers.
"""
import hashlib
from datetime import datetime
from typing import Optional
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import DocumentContent

logger = structlog.get_logger()


def _compute_content_hash(content: str) -> str:
    """SHA-256 hash of content string."""
    return hashlib.sha256(content.encode()).hexdigest()


class DocumentContentService:
    """
    Manages DocumentContent records — raw document text stored for re-embedding.

    Supports web (url-keyed) and file (file_path-keyed) sources.
    All mutation methods use an explicit db.flush() so callers control
    when the transaction is committed.
    """

    # ------------------------------------------------------------------ #
    # Lookups
    # ------------------------------------------------------------------ #

    async def get_by_id(
        self,
        db: AsyncSession,
        content_id: str,
    ) -> Optional[DocumentContent]:
        """Fetch a document by its primary key."""
        stmt = select(DocumentContent).where(DocumentContent.id == content_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_file_id(
        self,
        db: AsyncSession,
        source_id: str,
        file_id: str,
    ) -> Optional[DocumentContent]:
        """Fetch a document by source + file identifier (stored in the url column).

        The `url` column doubles as a file identifier for non-web sources — it
        holds the file path or a stable file URI so the uniqueness constraint works.
        """
        stmt = select(DocumentContent).where(
            DocumentContent.source_id == source_id,
            DocumentContent.url == file_id,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def search_by_title(
        self,
        db: AsyncSession,
        query: str,
        source_id: Optional[str] = None,
        limit: int = 10,
    ) -> list[DocumentContent]:
        """Fuzzy search by document title using ILIKE.

        Optionally constrained to a single source.
        """
        stmt = select(DocumentContent).where(
            DocumentContent.title.ilike(f"%{query}%")
        )
        if source_id:
            stmt = stmt.where(DocumentContent.source_id == source_id)
        stmt = stmt.order_by(DocumentContent.scraped_at.desc()).limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_source(
        self,
        db: AsyncSession,
        source_id: str,
    ) -> list[DocumentContent]:
        """Return all DocumentContent records for a knowledge source."""
        stmt = (
            select(DocumentContent)
            .where(DocumentContent.source_id == source_id)
            .order_by(DocumentContent.scraped_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------ #
    # Mutations
    # ------------------------------------------------------------------ #

    async def upsert(
        self,
        db: AsyncSession,
        source_id: str,
        url: str,
        raw_content: str,
        title: Optional[str] = None,
        file_path: Optional[str] = None,
        file_type: Optional[str] = None,
        document_type: Optional[str] = None,
        classification: Optional[dict] = None,
        taxonomy_id: Optional[str] = None,
        classification_method: Optional[str] = None,
        classification_taxonomy_version: Optional[int] = None,
        **kwargs,
    ) -> DocumentContent:
        """Insert or update a document record keyed on (source_id, url).

        Recalculates content_hash and content_length automatically.
        Extra kwargs are silently ignored to allow forward-compatible callers.
        """
        content_hash = _compute_content_hash(raw_content)

        existing = await self.get_by_file_id(db, source_id, url)

        if existing:
            existing.title = title
            existing.raw_content = raw_content
            existing.content_hash = content_hash
            existing.content_length = len(raw_content)
            existing.scraped_at = datetime.utcnow()
            if file_path is not None:
                existing.file_path = file_path
            if file_type is not None:
                existing.file_type = file_type
            if document_type is not None:
                existing.document_type = document_type
            if classification is not None:
                existing.classification = classification
            if taxonomy_id is not None:
                existing.taxonomy_id = taxonomy_id
            if classification_method is not None:
                existing.classification_method = classification_method
            if classification_taxonomy_version is not None:
                existing.classification_taxonomy_version = classification_taxonomy_version
            await db.flush()
            logger.debug("Updated document content", source_id=source_id, url=url)
            return existing

        doc = DocumentContent(
            source_id=source_id,
            url=url,
            title=title,
            raw_content=raw_content,
            content_hash=content_hash,
            content_length=len(raw_content),
            file_path=file_path,
            file_type=file_type,
            document_type=document_type,
            classification=classification,
            taxonomy_id=taxonomy_id,
            classification_method=classification_method,
            classification_taxonomy_version=classification_taxonomy_version,
        )
        db.add(doc)
        await db.flush()
        logger.debug("Created document content", source_id=source_id, url=url)
        return doc

    async def delete_by_file_id(
        self,
        db: AsyncSession,
        source_id: str,
        file_id: str,
    ) -> None:
        """Delete a document record by source + file identifier."""
        stmt = delete(DocumentContent).where(
            DocumentContent.source_id == source_id,
            DocumentContent.url == file_id,
        )
        await db.execute(stmt)
        await db.flush()
        logger.debug("Deleted document content", source_id=source_id, file_id=file_id)
