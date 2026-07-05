"""
Tests for source-deletion / file-removal vector routing.

A source's chunks live in its OWN collection (the primary copy the search path
reads) and, for a library-bound source, additionally in each bound library's
collection (mirror copies). Deletion must purge every copy:
- delete_source removes THIS source's chunks (by source_id) from each bound-
  library collection (without dropping the shared collection), and drops the
  source's own per-source collection.
- remove_files / remove_urls delete from the source's own collection AND each
  bound-library collection.
"""

from unittest.mock import MagicMock

import json
import pytest

from app.services.ingestion.source_manager import SourceManager
from app.models import Library, LibrarySource
from tests.factories import KnowledgeSourceFactory


async def _bind_library(db, source, collection_name: str) -> Library:
    lib = Library(name=f"Lib {collection_name}", collection_name=collection_name)
    db.add(lib)
    await db.flush()
    db.add(LibrarySource(library_id=lib.id, source_id=source.id))
    await db.flush()
    return lib


def _manager(db) -> SourceManager:
    mgr = SourceManager(db)
    mgr.client = MagicMock()
    return mgr


def _delete_collections(client) -> list[str]:
    return [c.kwargs.get("collection_name") for c in client.delete.call_args_list]


def _dropped_collections(client) -> list[str]:
    out = []
    for c in client.delete_collection.call_args_list:
        out.append(c.kwargs.get("collection_name") if c.kwargs else (c.args[0] if c.args else None))
    return out


@pytest.mark.asyncio
async def test_delete_bound_source_purges_library_chunks_and_drops_own(db_session):
    source = KnowledgeSourceFactory.create(
        name="Docs", source_type="directory", source_path="/data/documents",
        collection_name="source_own_coll",
    )
    db_session.add(source)
    await db_session.flush()
    await _bind_library(db_session, source, "lib_coll_a")
    await db_session.commit()

    mgr = _manager(db_session)
    await mgr.delete_source(source.id)

    # This source's chunks are purged from the shared library collection...
    assert "lib_coll_a" in _delete_collections(mgr.client)
    # ...but the shared library collection is NOT dropped.
    assert "lib_coll_a" not in _dropped_collections(mgr.client)
    # The source's own (per-source) collection IS dropped.
    assert "source_own_coll" in _dropped_collections(mgr.client)


@pytest.mark.asyncio
async def test_delete_unbound_source_drops_own_collection(db_session):
    source = KnowledgeSourceFactory.create(
        name="Docs", source_type="directory", source_path="/data/documents",
        collection_name="source_own_coll",
    )
    db_session.add(source)
    await db_session.commit()

    mgr = _manager(db_session)
    await mgr.delete_source(source.id)

    assert "source_own_coll" in _dropped_collections(mgr.client)


@pytest.mark.asyncio
async def test_delete_sub_source_touches_no_qdrant(db_session):
    root = KnowledgeSourceFactory.create(
        name="Root", source_type="directory", source_path="/data/documents",
        collection_name="root_coll",
    )
    db_session.add(root)
    await db_session.flush()
    sub = KnowledgeSourceFactory.create(
        name="Sub", source_type="directory", source_path="/data/documents",
    )
    sub.parent_source_id = root.id
    sub.path_prefix = "/data/documents/Alpha"
    sub.collection_name = None
    db_session.add(sub)
    await db_session.commit()

    mgr = _manager(db_session)
    await mgr.delete_source(sub.id)

    assert mgr.client.delete_collection.call_count == 0
    assert mgr.client.delete.call_count == 0


@pytest.mark.asyncio
async def test_remove_files_bound_deletes_from_library_collection(db_session):
    source = KnowledgeSourceFactory.create(
        name="Uploads", source_type="file", source_path="/uploads",
        collection_name="source_own_coll",
    )
    source.selected_files = json.dumps([
        {"path": "/app/uploads/report.pdf", "original_name": "report.pdf", "size_bytes": 10},
        {"path": "/app/uploads/keep.pdf", "original_name": "keep.pdf", "size_bytes": 10},
    ])
    db_session.add(source)
    await db_session.flush()
    await _bind_library(db_session, source, "lib_coll_a")
    await db_session.commit()

    mgr = _manager(db_session)
    await mgr.remove_files_from_source(source.id, ["/app/uploads/report.pdf"])

    # Chunks live in the source's own collection (primary, what search reads)
    # AND each bound library's collection (mirror) — purge from both.
    assert "lib_coll_a" in _delete_collections(mgr.client)
    assert "source_own_coll" in _delete_collections(mgr.client)


@pytest.mark.asyncio
async def test_remove_urls_bound_deletes_from_library_collection(db_session):
    source = KnowledgeSourceFactory.create(
        name="Site", source_type="url", source_path="https://example.com",
        collection_name="source_own_coll",
    )
    source.selected_urls = json.dumps([
        "https://example.com/a", "https://example.com/b",
    ])
    db_session.add(source)
    await db_session.flush()
    await _bind_library(db_session, source, "lib_coll_a")
    await db_session.commit()

    mgr = _manager(db_session)
    await mgr.remove_urls_from_source(source.id, ["https://example.com/a"])

    # Chunks live in the source's own collection (primary, what search reads)
    # AND each bound library's collection (mirror) — purge from both.
    assert "lib_coll_a" in _delete_collections(mgr.client)
    assert "source_own_coll" in _delete_collections(mgr.client)
