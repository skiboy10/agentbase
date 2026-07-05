"""
Tests for sub-source document counting.

Sub-sources are filtered *views* over a parent directory root's files (scoped by
path_prefix). They are never indexed independently, so their stored
``document_count`` column is always 0. The real count must be derived from the
PARENT's document_content rows whose path falls under the sub-source's prefix.

These tests pin that derivation (get_sub_source_document_counts) and the
source_to_response override that surfaces it.
"""

import pytest

from app.api.sources.helpers import (
    get_sub_source_document_counts,
    source_to_response,
)
from app.models import DocumentContent
from tests.factories import KnowledgeSourceFactory


def _doc(source_id: str, url: str) -> DocumentContent:
    return DocumentContent(
        source_id=source_id,
        url=url,
        raw_content="x",
        content_hash="h",
    )


async def _make_tree(db_session):
    """A directory root with docs in two subfolders + a top-level doc."""
    root = KnowledgeSourceFactory.create(
        name="Work Documents", source_type="directory", source_path="/data/documents"
    )
    db_session.add(root)
    await db_session.flush()

    db_session.add_all([
        _doc(root.id, "/data/documents/Alpha/one.pdf"),
        _doc(root.id, "/data/documents/Alpha/two.pptx"),
        _doc(root.id, "/data/documents/Alpha/Nested/three.docx"),
        _doc(root.id, "/data/documents/Beta/four.pdf"),
        _doc(root.id, "/data/documents/top-level.md"),
    ])

    alpha = KnowledgeSourceFactory.create(
        name="Alpha", source_type="directory", source_path="/data/documents",
    )
    alpha.parent_source_id = root.id
    alpha.path_prefix = "/data/documents/Alpha"

    beta = KnowledgeSourceFactory.create(
        name="Beta", source_type="directory", source_path="/data/documents",
    )
    beta.parent_source_id = root.id
    beta.path_prefix = "/data/documents/Beta/"  # trailing slash should not matter

    db_session.add_all([alpha, beta])
    await db_session.commit()
    return root, alpha, beta


@pytest.mark.asyncio
async def test_counts_docs_under_prefix(db_session):
    root, alpha, beta = await _make_tree(db_session)
    counts = await get_sub_source_document_counts(db_session, [alpha, beta])
    assert counts[alpha.id] == 3   # two direct + one nested under Alpha/
    assert counts[beta.id] == 1


@pytest.mark.asyncio
async def test_prefix_is_not_substring_matched(db_session):
    """A prefix must match a path *segment*, not a bare string prefix."""
    root = KnowledgeSourceFactory.create(
        name="Root", source_type="directory", source_path="/data/documents"
    )
    db_session.add(root)
    await db_session.flush()
    # 'AlphaBeta' must NOT be counted under the 'Alpha' sub-source.
    db_session.add_all([
        _doc(root.id, "/data/documents/Alpha/in.pdf"),
        _doc(root.id, "/data/documents/AlphaBeta/out.pdf"),
    ])
    sub = KnowledgeSourceFactory.create(
        name="Alpha", source_type="directory", source_path="/data/documents",
    )
    sub.parent_source_id = root.id
    sub.path_prefix = "/data/documents/Alpha"
    db_session.add(sub)
    await db_session.commit()

    counts = await get_sub_source_document_counts(db_session, [sub])
    assert counts[sub.id] == 1


@pytest.mark.asyncio
async def test_non_sub_sources_are_ignored(db_session):
    root = KnowledgeSourceFactory.create(
        name="Root", source_type="directory", source_path="/data/documents"
    )
    db_session.add(root)
    await db_session.commit()
    # A root (no parent) yields no derived count entry.
    counts = await get_sub_source_document_counts(db_session, [root])
    assert root.id not in counts


@pytest.mark.asyncio
async def test_response_override_surfaces_derived_count(db_session):
    root, alpha, beta = await _make_tree(db_session)
    # Stored column is 0 for sub-sources; the override must win.
    assert alpha.document_count == 0
    resp = source_to_response(alpha, document_count_override=3)
    assert resp.document_count == 3
    # Without an override, the stored column is used (root behaviour unchanged).
    root_resp = source_to_response(root)
    assert root_resp.document_count == root.document_count
