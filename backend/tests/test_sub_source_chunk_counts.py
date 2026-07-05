"""
Tests for sub-source chunk counting.

Sub-sources are filtered *views* over a parent directory root's content (scoped
by path_prefix). They own no chunks of their own, so their stored ``chunk_count``
column is always 0. The real count is the sum of the PARENT's per-document
``chunk_count`` (``documents`` table) whose ``file_path`` falls under the
sub-source's prefix — a Postgres sum that is collection-agnostic (chunks may
physically live in a library's collection, so the source's own collection_name
is not a reliable handle).

These tests pin that derivation (get_sub_source_chunk_counts) and the
source_to_response override that surfaces it.
"""

import uuid

import pytest

from app.api.sources.helpers import (
    get_sub_source_chunk_counts,
    source_to_response,
)
from app.models import Document, Library
from tests.factories import KnowledgeSourceFactory


async def _make_library(db_session) -> Library:
    kb = Library(
        id=str(uuid.uuid4()),
        name="Docs",
        collection_name=f"agentbase_kb_t_{uuid.uuid4().hex[:8]}",
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:4b",
        embedding_dimensions=1024,
    )
    db_session.add(kb)
    await db_session.flush()
    return kb


def _doc(library_id: str, source_id: str, file_path: str, chunk_count: int) -> Document:
    return Document(
        id=str(uuid.uuid4()),
        library_id=library_id,
        source_id=source_id,
        document_id=f"{source_id[:8]}:{uuid.uuid4().hex[:16]}",
        file_path=file_path,
        chunk_count=chunk_count,
        full_text="",
        text_length=0,
        status="indexed",
    )


async def _make_tree(db_session):
    """A directory root with library documents in two subfolders + a top-level doc."""
    kb = await _make_library(db_session)
    root = KnowledgeSourceFactory.create(
        name="Work Documents", source_type="directory", source_path="/data/documents"
    )
    db_session.add(root)
    await db_session.flush()

    db_session.add_all([
        _doc(kb.id, root.id, "/data/documents/Alpha/one.pdf", 5),
        _doc(kb.id, root.id, "/data/documents/Alpha/two.pptx", 3),
        _doc(kb.id, root.id, "/data/documents/Alpha/Nested/three.docx", 2),
        _doc(kb.id, root.id, "/data/documents/Beta/four.pdf", 7),
        _doc(kb.id, root.id, "/data/documents/top-level.md", 9),
    ])

    alpha = KnowledgeSourceFactory.create(
        name="Alpha", source_type="directory", source_path="/data/documents"
    )
    alpha.parent_source_id = root.id
    alpha.path_prefix = "/data/documents/Alpha"

    beta = KnowledgeSourceFactory.create(
        name="Beta", source_type="directory", source_path="/data/documents"
    )
    beta.parent_source_id = root.id
    beta.path_prefix = "/data/documents/Beta/"  # trailing slash should not matter

    db_session.add_all([alpha, beta])
    await db_session.commit()
    return root, alpha, beta


@pytest.mark.asyncio
async def test_sums_chunks_under_prefix(db_session):
    root, alpha, beta = await _make_tree(db_session)
    counts = await get_sub_source_chunk_counts(db_session, [root, alpha, beta])
    assert counts[alpha.id] == 10  # 5 + 3 direct + 2 nested under Alpha/
    assert counts[beta.id] == 7


@pytest.mark.asyncio
async def test_prefix_is_not_substring_matched(db_session):
    """A prefix must match a path *segment*, not a bare string prefix."""
    kb = await _make_library(db_session)
    root = KnowledgeSourceFactory.create(
        name="Root", source_type="directory", source_path="/data/documents"
    )
    db_session.add(root)
    await db_session.flush()
    # 'AlphaBeta' must NOT be summed under the 'Alpha' sub-source.
    db_session.add_all([
        _doc(kb.id, root.id, "/data/documents/Alpha/in.pdf", 4),
        _doc(kb.id, root.id, "/data/documents/AlphaBeta/out.pdf", 6),
    ])
    sub = KnowledgeSourceFactory.create(
        name="Alpha", source_type="directory", source_path="/data/documents"
    )
    sub.parent_source_id = root.id
    sub.path_prefix = "/data/documents/Alpha"
    db_session.add(sub)
    await db_session.commit()

    counts = await get_sub_source_chunk_counts(db_session, [sub])
    assert counts[sub.id] == 4


@pytest.mark.asyncio
async def test_multi_library_binding_is_not_double_counted(db_session):
    """The same file indexed into two libraries counts once, not twice."""
    kb1 = await _make_library(db_session)
    kb2 = await _make_library(db_session)
    root = KnowledgeSourceFactory.create(
        name="Root", source_type="directory", source_path="/data/documents"
    )
    db_session.add(root)
    await db_session.flush()
    db_session.add_all([
        _doc(kb1.id, root.id, "/data/documents/Alpha/one.pdf", 5),
        _doc(kb2.id, root.id, "/data/documents/Alpha/one.pdf", 5),  # same file, 2nd library
    ])
    sub = KnowledgeSourceFactory.create(
        name="Alpha", source_type="directory", source_path="/data/documents"
    )
    sub.parent_source_id = root.id
    sub.path_prefix = "/data/documents/Alpha"
    db_session.add(sub)
    await db_session.commit()

    counts = await get_sub_source_chunk_counts(db_session, [sub])
    assert counts[sub.id] == 5  # de-duplicated per (source_id, file_path)


@pytest.mark.asyncio
async def test_non_sub_sources_are_ignored(db_session):
    root = KnowledgeSourceFactory.create(
        name="Root", source_type="directory", source_path="/data/documents"
    )
    db_session.add(root)
    await db_session.commit()
    counts = await get_sub_source_chunk_counts(db_session, [root])
    assert root.id not in counts


@pytest.mark.asyncio
async def test_zero_when_no_documents(db_session):
    """A sub-source whose parent has no library documents yields 0, not an error."""
    root = KnowledgeSourceFactory.create(
        name="Root", source_type="directory", source_path="/data/documents"
    )
    db_session.add(root)
    await db_session.flush()
    sub = KnowledgeSourceFactory.create(
        name="Alpha", source_type="directory", source_path="/data/documents"
    )
    sub.parent_source_id = root.id
    sub.path_prefix = "/data/documents/Alpha"
    db_session.add(sub)
    await db_session.commit()

    counts = await get_sub_source_chunk_counts(db_session, [root, sub])
    assert counts[sub.id] == 0


@pytest.mark.asyncio
async def test_response_override_surfaces_derived_chunk_count(db_session):
    """The override must win over the always-0 stored column for sub-sources."""
    root, alpha, beta = await _make_tree(db_session)
    root.chunk_count = 500

    assert alpha.chunk_count == 0  # stored column is always 0 for sub-sources
    resp = source_to_response(alpha, chunk_count_override=10)
    assert resp.chunk_count == 10

    # Without an override, the stored column is used (root behaviour unchanged).
    root_resp = source_to_response(root)
    assert root_resp.chunk_count == 500
