"""
Tests for the Library documents API and stat recalculation.

Covers the new schema/filter behaviour:
- ``DocumentResponse.source_name`` is populated from Source.name
- ``file_type`` and ``document_type`` filters reduce both list + total
- ``LibraryService._compute_kb_stats`` counts rows in the documents table
  (regardless of denormalised Source.document_count values)
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Library, LibrarySource, Source, Document
from app.services.library import LibraryService


# ------------------------------------------------------------------ #
# Fixture helpers
# ------------------------------------------------------------------ #

async def _make_library(db: AsyncSession, name: str = "Docs Library") -> Library:
    kb_id = str(uuid.uuid4())
    kb = Library(
        id=kb_id,
        name=name,
        collection_name=f"agentbase_kb_t_{kb_id[:8]}",
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:4b",
        embedding_dimensions=1024,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)
    return kb


async def _make_source(db: AsyncSession, name: str = "Source") -> Source:
    src = Source(
        id=str(uuid.uuid4()),
        name=name,
        source_type="url",
        source_path="https://example.com",
        status="indexed",
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:4b",
        embedding_dimensions=1024,
        collection_name=f"agentbase_src_{uuid.uuid4().hex[:8]}",
        document_count=999,  # Deliberately wrong — should not influence KB stats
        chunk_count=999,
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)
    return src


async def _bind(db: AsyncSession, kb: Library, src: Source) -> None:
    db.add(LibrarySource(library_id=kb.id, source_id=src.id))
    await db.commit()


async def _make_doc(
    db: AsyncSession,
    kb: Library,
    src: Source,
    *,
    title: str,
    file_type: str = "url",
    document_type: str = "standard",
    chunk_count: int = 1,
) -> Document:
    doc = Document(
        id=str(uuid.uuid4()),
        library_id=kb.id,
        source_id=src.id,
        document_id=f"{src.id[:8]}:{uuid.uuid4().hex[:16]}",
        title=title,
        file_type=file_type,
        document_type=document_type,
        chunk_count=chunk_count,
        full_text="",
        text_length=0,
        status="indexed",
        indexed_at=datetime.utcnow(),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


# ------------------------------------------------------------------ #
# API tests — source_name + filters
# ------------------------------------------------------------------ #

class TestDocumentsApi:
    @pytest.mark.asyncio
    async def test_list_documents_includes_source_name(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        kb = await _make_library(db_session, "API Library")
        src = await _make_source(db_session, name="ACME Docs Site")
        await _bind(db_session, kb, src)
        await _make_doc(db_session, kb, src, title="ACME Login Flow")

        resp = await client.get(f"/api/libraries/{kb.id}/documents")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["documents"]) == 1
        doc = body["documents"][0]
        # The defect this test guards against: blank Source column in UI
        assert doc["source_name"] == "ACME Docs Site"
        assert doc["title"] == "ACME Login Flow"

    @pytest.mark.asyncio
    async def test_list_documents_filter_by_file_type(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        kb = await _make_library(db_session, "Mixed Types Library")
        src = await _make_source(db_session, name="Mixed Source")
        await _bind(db_session, kb, src)

        await _make_doc(db_session, kb, src, title="A", file_type="url")
        await _make_doc(db_session, kb, src, title="B", file_type="url")
        await _make_doc(db_session, kb, src, title="C", file_type="pdf")

        all_resp = await client.get(f"/api/libraries/{kb.id}/documents")
        assert all_resp.status_code == 200
        assert all_resp.json()["total"] == 3

        url_resp = await client.get(
            f"/api/libraries/{kb.id}/documents?file_type=url"
        )
        assert url_resp.status_code == 200
        body = url_resp.json()
        assert body["total"] == 2
        assert len(body["documents"]) == 2
        assert {d["file_type"] for d in body["documents"]} == {"url"}

        pdf_resp = await client.get(
            f"/api/libraries/{kb.id}/documents?file_type=pdf"
        )
        assert pdf_resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_list_documents_filter_by_document_type(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        kb = await _make_library(db_session, "DocType Library")
        src = await _make_source(db_session, name="DocType Source")
        await _bind(db_session, kb, src)

        await _make_doc(db_session, kb, src, title="A", document_type="standard")
        await _make_doc(db_session, kb, src, title="B", document_type="standard")
        await _make_doc(db_session, kb, src, title="C", document_type="reference")

        ref = await client.get(
            f"/api/libraries/{kb.id}/documents?document_type=reference"
        )
        assert ref.status_code == 200
        body = ref.json()
        assert body["total"] == 1
        assert body["documents"][0]["document_type"] == "reference"

        std = await client.get(
            f"/api/libraries/{kb.id}/documents?document_type=standard"
        )
        assert std.json()["total"] == 2


# ------------------------------------------------------------------ #
# Service tests — recalculate_stats counts rows in documents table
# ------------------------------------------------------------------ #

class TestRecalculateStats:
    @pytest.mark.asyncio
    async def test_recalculate_stats_counts_documents_rows(
        self, db_session: AsyncSession
    ):
        kb = await _make_library(db_session, "Stat Library")
        src = await _make_source(db_session, name="Stat Source")
        # Source claims a wildly inflated doc count; recalc must IGNORE it
        # and trust the rows in `documents`.
        assert src.document_count == 999
        await _bind(db_session, kb, src)

        # Insert 5 real Document rows with chunk_count=3 each → expect
        # document_count=5, chunk_count=15
        for i in range(5):
            await _make_doc(
                db_session, kb, src, title=f"Doc {i}", chunk_count=3,
            )

        service = LibraryService(db_session)
        updated = await service.recalculate_stats(kb.id)
        assert updated is not None
        assert updated.source_count == 1
        assert updated.document_count == 5
        assert updated.chunk_count == 15

    @pytest.mark.asyncio
    async def test_recalculate_stats_zero_documents(
        self, db_session: AsyncSession
    ):
        """Empty library still recalcs correctly — guards against the old
        bug where the card showed Source.document_count even when the
        documents table had zero rows."""
        kb = await _make_library(db_session, "Empty Library")
        src = await _make_source(db_session, name="Empty Source")
        await _bind(db_session, kb, src)

        service = LibraryService(db_session)
        updated = await service.recalculate_stats(kb.id)
        assert updated is not None
        assert updated.source_count == 1
        assert updated.document_count == 0
        assert updated.chunk_count == 0
