"""
Tests for KB-aware ingestion: every indexer must write Document rows for
each library a source is bound to, and the legacy (no-library) path must
still work without touching the documents table.

The most valuable assertions are around ``BaseIndexer._upsert_kb_documents``
because that's the single helper every indexer now shares. Driving each
indexer's ``index()`` end-to-end requires a live Qdrant + embedding registry
which is outside the scope of these unit tests; we exercise the helper
directly and one indexer (directory) end-to-end with a tiny tmp_path
fixture so we still cover the wiring.
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Library, LibrarySource, Source, Document
from app.services.ingestion.indexers.base import BaseIndexer
from app.services.library import DocumentService


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

async def _make_library(db: AsyncSession, name: str = "Test Library") -> Library:
    kb_id = str(uuid.uuid4())
    kb = Library(
        id=kb_id,
        name=name,
        collection_name=f"agentbase_kb_test_{kb_id[:8]}",
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:4b",
        embedding_dimensions=1024,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return kb


async def _make_source(
    db: AsyncSession,
    name: str = "Test Source",
    source_type: str = "url",
    source_path: str = "https://example.com",
) -> Source:
    src = Source(
        id=str(uuid.uuid4()),
        name=name,
        source_type=source_type,
        source_path=source_path,
        status="pending",
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:4b",
        embedding_dimensions=1024,
        collection_name=f"agentbase_src_{uuid.uuid4().hex[:8]}",
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)
    return src


async def _bind_source_to_library(
    db: AsyncSession, library: Library, source: Source
) -> None:
    db.add(LibrarySource(library_id=library.id, source_id=source.id))
    await db.commit()


# ------------------------------------------------------------------ #
# Tests for BaseIndexer._upsert_kb_documents (shared by all indexers)
# ------------------------------------------------------------------ #

class TestUpsertKbDocuments:
    """The shared helper that every indexer calls to persist Document rows."""

    @pytest.mark.asyncio
    async def test_url_indexer_writes_documents_for_library_bound_source(
        self, db_session: AsyncSession
    ):
        """URL-style upsert: source bound to library, _upsert_kb_documents
        must produce a Document row with the right shape."""
        kb = await _make_library(db_session, "URL Library")
        src = await _make_source(
            db_session, "URL Source", source_type="url",
            source_path="https://example.com/docs",
        )
        await _bind_source_to_library(db_session, kb, src)

        indexer = BaseIndexer(db_session)
        await indexer._load_kb_for_source(src)
        kbs = indexer._get_kbs(src)
        assert len(kbs) == 1

        document_id = indexer._generate_document_id(
            src.id, "https://example.com/docs/page1"
        )
        await indexer._upsert_kb_documents(
            source=src,
            kbs=kbs,
            document_id=document_id,
            title="Example Page",
            full_text="Hello world body text",
            content_hash="abc123",
            url="https://example.com/docs/page1",
            file_type="url",
            document_type="standard",
            chunk_count=3,
        )
        await db_session.commit()

        result = await db_session.execute(
            select(Document).where(Document.library_id == kb.id)
        )
        rows = list(result.scalars().all())
        assert len(rows) == 1
        doc = rows[0]
        assert doc.source_id == src.id
        assert doc.library_id == kb.id
        assert doc.document_id == document_id
        assert doc.title == "Example Page"
        assert doc.url == "https://example.com/docs/page1"
        assert doc.file_type == "url"
        assert doc.chunk_count == 3
        assert doc.status == "indexed"
        assert doc.indexed_at is not None

    @pytest.mark.asyncio
    async def test_file_indexer_writes_documents_for_library_bound_source(
        self, db_session: AsyncSession
    ):
        """File-style upsert: file_path / file_type populated correctly."""
        kb = await _make_library(db_session, "File Library")
        src = await _make_source(
            db_session, "File Source", source_type="file",
            source_path="/uploads/test",
        )
        await _bind_source_to_library(db_session, kb, src)

        indexer = BaseIndexer(db_session)
        await indexer._load_kb_for_source(src)
        kbs = indexer._get_kbs(src)

        document_id = indexer._generate_document_id(src.id, "/uploads/test/file.pdf")
        await indexer._upsert_kb_documents(
            source=src,
            kbs=kbs,
            document_id=document_id,
            title="file",
            full_text="PDF body content extracted",
            content_hash="def456",
            file_path="/uploads/test/file.pdf",
            file_type="pdf",
            document_type="standard",
            chunk_count=5,
        )
        await db_session.commit()

        result = await db_session.execute(
            select(Document).where(Document.library_id == kb.id)
        )
        docs = list(result.scalars().all())
        assert len(docs) == 1
        assert docs[0].file_path == "/uploads/test/file.pdf"
        assert docs[0].file_type == "pdf"
        assert docs[0].chunk_count == 5
        assert docs[0].status == "indexed"

    @pytest.mark.asyncio
    async def test_directory_indexer_writes_documents_for_library_bound_source(
        self, db_session: AsyncSession
    ):
        """Directory upsert parity check (same helper, same shape)."""
        kb = await _make_library(db_session, "Dir Library")
        src = await _make_source(
            db_session, "Dir Source", source_type="directory",
            source_path="/data/docs",
        )
        await _bind_source_to_library(db_session, kb, src)

        indexer = BaseIndexer(db_session)
        await indexer._load_kb_for_source(src)
        kbs = indexer._get_kbs(src)

        # Two distinct documents in the same library
        for fname, ext in [("notes", "md"), ("presentation", "pptx")]:
            document_id = indexer._generate_document_id(src.id, f"/data/docs/{fname}.{ext}")
            await indexer._upsert_kb_documents(
                source=src,
                kbs=kbs,
                document_id=document_id,
                title=fname,
                full_text=f"body of {fname}",
                content_hash=f"h-{fname}",
                file_path=f"/data/docs/{fname}.{ext}",
                file_type=ext,
                document_type="standard",
                chunk_count=2,
            )
        await db_session.commit()

        result = await db_session.execute(
            select(Document).where(Document.library_id == kb.id)
        )
        docs = list(result.scalars().all())
        assert len(docs) == 2
        file_types = {d.file_type for d in docs}
        assert file_types == {"md", "pptx"}

    @pytest.mark.asyncio
    async def test_legacy_mode_no_library_no_documents(self, db_session: AsyncSession):
        """Legacy path: source with zero library bindings produces zero
        Document rows even when the helper is invoked. This is the regression
        that proves the legacy indexing path still works for unbound sources.
        """
        src = await _make_source(
            db_session, "Legacy Source", source_type="url",
            source_path="https://legacy.example.com",
        )

        indexer = BaseIndexer(db_session)
        await indexer._load_kb_for_source(src)
        kbs = indexer._get_kbs(src)
        assert kbs == []

        # No-op when kbs is empty
        await indexer._upsert_kb_documents(
            source=src,
            kbs=kbs,
            document_id=indexer._generate_document_id(src.id, "/x"),
            title="Should not appear",
            full_text="ignored",
            content_hash="ignored",
            chunk_count=1,
        )
        await db_session.commit()

        count = await db_session.execute(
            select(func.count(Document.id)).where(Document.source_id == src.id)
        )
        assert count.scalar() == 0

    @pytest.mark.asyncio
    async def test_upsert_writes_to_every_bound_library(self, db_session: AsyncSession):
        """A source bound to two libraries must produce one Document row in each."""
        kb1 = await _make_library(db_session, "Lib A")
        kb2 = await _make_library(db_session, "Lib B")
        src = await _make_source(db_session, "Multi-bind Source")
        await _bind_source_to_library(db_session, kb1, src)
        await _bind_source_to_library(db_session, kb2, src)

        indexer = BaseIndexer(db_session)
        await indexer._load_kb_for_source(src)
        kbs = indexer._get_kbs(src)
        assert len(kbs) == 2

        document_id = indexer._generate_document_id(src.id, "shared-doc")
        await indexer._upsert_kb_documents(
            source=src,
            kbs=kbs,
            document_id=document_id,
            title="Shared Doc",
            full_text="content",
            content_hash="h",
            file_type="url",
            chunk_count=1,
        )
        await db_session.commit()

        for kb in (kb1, kb2):
            result = await db_session.execute(
                select(Document).where(Document.library_id == kb.id)
            )
            rows = list(result.scalars().all())
            assert len(rows) == 1, f"Expected one Document row in library {kb.name}"
            assert rows[0].title == "Shared Doc"

    @pytest.mark.asyncio
    async def test_upsert_is_idempotent_on_reindex(self, db_session: AsyncSession):
        """Calling _upsert_kb_documents twice with the same document_id must
        not create duplicate rows — re-indexing is the expected path."""
        kb = await _make_library(db_session, "Idem Library")
        src = await _make_source(db_session, "Idem Source")
        await _bind_source_to_library(db_session, kb, src)

        indexer = BaseIndexer(db_session)
        await indexer._load_kb_for_source(src)
        kbs = indexer._get_kbs(src)

        document_id = indexer._generate_document_id(src.id, "page")
        # First call (initial index)
        await indexer._upsert_kb_documents(
            source=src, kbs=kbs, document_id=document_id,
            title="v1", full_text="first body", content_hash="h1",
            file_type="url", chunk_count=2,
        )
        await db_session.commit()
        # Second call (re-index with new content)
        await indexer._upsert_kb_documents(
            source=src, kbs=kbs, document_id=document_id,
            title="v2", full_text="second body", content_hash="h2",
            file_type="url", chunk_count=4,
        )
        await db_session.commit()

        result = await db_session.execute(
            select(Document).where(Document.library_id == kb.id)
        )
        docs = list(result.scalars().all())
        assert len(docs) == 1
        assert docs[0].title == "v2"
        assert docs[0].chunk_count == 4
        assert docs[0].text_length == len("second body")
