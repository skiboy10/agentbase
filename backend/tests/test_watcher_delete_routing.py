"""
Tests for watcher delete-routing across the correct Qdrant collection(s).

A directory source's chunks live in its OWN collection (the primary copy the
RAG read path queries) and, when library-bound, additionally in each bound
library's collection (mirror copies). The file-deletion paths (watcher
_handle_delete, force_sync) must resolve and delete from ALL of them, keyed by
the same root-relative path the writer uses — otherwise stale chunks for deleted
files linger where RAG actually reads.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.ingestion.watcher import (
    DirectoryWatcher,
    _resolve_target_collections,
)
from app.models import Library, LibrarySource
from tests.factories import KnowledgeSourceFactory


async def _bind_library(db, source, collection_name: str) -> Library:
    lib = Library(name=f"Lib {collection_name}", collection_name=collection_name)
    db.add(lib)
    await db.flush()
    db.add(LibrarySource(library_id=lib.id, source_id=source.id))
    await db.flush()
    return lib


# ---------------------------------------------------------------------------
# _resolve_target_collections — the core routing logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bound_source_resolves_to_own_and_library_collections(db_session):
    source = KnowledgeSourceFactory.create(
        name="Docs", source_type="directory", source_path="/data/documents",
        collection_name="source_own_coll",
    )
    db_session.add(source)
    await db_session.flush()
    await _bind_library(db_session, source, "lib_coll_a")
    await _bind_library(db_session, source, "lib_coll_b")
    await db_session.commit()

    cols = await _resolve_target_collections(db_session, source.id, source.collection_name)
    # Source's own collection (primary) plus every bound library (mirror).
    assert set(cols) == {"source_own_coll", "lib_coll_a", "lib_coll_b"}


@pytest.mark.asyncio
async def test_unbound_source_resolves_to_own_collection(db_session):
    source = KnowledgeSourceFactory.create(
        name="Docs", source_type="directory", source_path="/data/documents",
        collection_name="source_own_coll",
    )
    db_session.add(source)
    await db_session.commit()

    cols = await _resolve_target_collections(db_session, source.id, source.collection_name)
    assert cols == ["source_own_coll"]


@pytest.mark.asyncio
async def test_unbound_source_without_collection_resolves_empty(db_session):
    source = KnowledgeSourceFactory.create(
        name="Docs", source_type="directory", source_path="/data/documents",
    )
    source.collection_name = None
    db_session.add(source)
    await db_session.commit()

    cols = await _resolve_target_collections(db_session, source.id, None)
    assert cols == []


# ---------------------------------------------------------------------------
# _handle_delete routes the Qdrant delete to the library collection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_handle_delete_targets_own_and_library_collections(db_session):
    source = KnowledgeSourceFactory.create(
        name="Docs", source_type="directory", source_path="/data/documents",
        collection_name="source_own_coll",
    )
    db_session.add(source)
    await db_session.flush()
    await _bind_library(db_session, source, "lib_coll_a")
    await db_session.commit()

    watcher = DirectoryWatcher(
        source.id, source.source_path, {"collection_name": source.collection_name}
    )

    mock_client = MagicMock()
    with patch(
        "app.services.ingestion.watcher.get_qdrant_client", return_value=mock_client
    ):
        await watcher._handle_delete(db_session, "/data/documents/Alpha/report.pdf")

    targeted = [c.kwargs["collection_name"] for c in mock_client.delete.call_args_list]
    # Purge from the source's own collection (primary) AND the library mirror.
    assert set(targeted) == {"source_own_coll", "lib_coll_a"}
