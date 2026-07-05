"""
Collection routing for library-bound sources.

The search/chat/coverage read path resolves a source's chunks via
``Source.collection_name``. Therefore the indexer MUST treat the source's own
collection as the primary (searchable) write target — even when the source is
bound to a library — and may additionally mirror chunks into each bound
library's collection.

Regression: before this fix, ``_get_collection_for_source`` returned the
*library* collection for a bound source, so everything indexed after binding
landed in a collection the read path never queries (invisible to search).
"""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Library, LibrarySource, Source
from app.services.ingestion.indexers.base import BaseIndexer


async def _make_library(db: AsyncSession, name: str) -> Library:
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


async def _make_source(db: AsyncSession, name: str) -> Source:
    src = Source(
        id=str(uuid.uuid4()),
        name=name,
        source_type="url",
        source_path="https://example.com",
        status="pending",
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:4b",
        embedding_dimensions=1024,
        collection_name=f"kb_src_{uuid.uuid4().hex[:8]}",
    )
    db.add(src)
    await db.commit()
    await db.refresh(src)
    return src


async def _bind(db: AsyncSession, library: Library, source: Source) -> None:
    db.add(LibrarySource(library_id=library.id, source_id=source.id))
    await db.commit()


class TestCollectionRouting:
    @pytest.mark.asyncio
    async def test_bound_source_primary_collection_is_source_own(
        self, db_session: AsyncSession
    ):
        """The primary write/read collection for a library-bound source is the
        source's own collection_name — what the search path reads — NOT the
        library collection."""
        kb = await _make_library(db_session, "Routing Lib")
        src = await _make_source(db_session, "Routing Source")
        await _bind(db_session, kb, src)

        indexer = BaseIndexer(db_session)
        await indexer._load_kb_for_source(src)

        assert indexer._get_collection_for_source(src) == src.collection_name
        assert indexer._get_collection_for_source(src) != kb.collection_name

    @pytest.mark.asyncio
    async def test_bound_source_mirrors_into_every_library_collection(
        self, db_session: AsyncSession
    ):
        """Chunks mirror into every bound library's collection (so those
        collections stay populated), while the source's own collection stays
        primary."""
        kb1 = await _make_library(db_session, "Lib A")
        kb2 = await _make_library(db_session, "Lib B")
        src = await _make_source(db_session, "Multi-bind Source")
        await _bind(db_session, kb1, src)
        await _bind(db_session, kb2, src)

        indexer = BaseIndexer(db_session)
        await indexer._load_kb_for_source(src)

        mirrors = indexer._get_library_mirror_collections(src)
        assert {coll for coll, _ in mirrors} == {kb1.collection_name, kb2.collection_name}
        assert {lib_id for _, lib_id in mirrors} == {kb1.id, kb2.id}
        # Primary is never one of the library collections.
        assert indexer._get_collection_for_source(src) == src.collection_name

    @pytest.mark.asyncio
    async def test_unbound_source_has_no_mirrors_and_owns_primary(
        self, db_session: AsyncSession
    ):
        """Legacy path: an unbound source writes only to its own collection and
        has no mirror targets."""
        src = await _make_source(db_session, "Legacy Source")

        indexer = BaseIndexer(db_session)
        await indexer._load_kb_for_source(src)

        assert indexer._get_collection_for_source(src) == src.collection_name
        assert indexer._get_library_mirror_collections(src) == []
