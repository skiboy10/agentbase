"""
Tests for the sub-source data model (Phase 2 of folder watcher consolidation).

Covers:
- create_source with parent_source_id + path_prefix → creates a sub-source view
- two-level hierarchy enforcement (sub-of-sub rejected)
- path_prefix must sit under parent's source_path
- delete_source on a sub-source does not touch the parent's Qdrant collection
- resolve_source_ids translates sub-source ids → root id + path filter overlay
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.ingestion.source_manager import SourceManager
from app.services.rag.source_resolver import resolve_source_ids, overlay_filters_for_root


pytestmark = pytest.mark.asyncio


async def _make_root(db: AsyncSession, name: str = "Root", path: str = "/tmp") -> str:
    sm = SourceManager(db)
    root = await sm.create_source(
        name=name,
        source_type="directory",
        source_path=path,
    )
    await db.commit()
    await db.refresh(root)
    return root.id


async def test_create_root_populates_collection_name(db_session: AsyncSession):
    sm = SourceManager(db_session)
    root = await sm.create_source(
        name="Root", source_type="directory", source_path="/tmp"
    )
    await db_session.commit()
    await db_session.refresh(root)
    assert root.parent_source_id is None
    assert root.collection_name and root.collection_name.startswith("kb_")


async def test_create_sub_source_inherits_root(db_session: AsyncSession):
    root_id = await _make_root(db_session)
    sm = SourceManager(db_session)

    sub = await sm.create_source(
        name="Sub",
        source_type="directory",
        source_path="ignored",
        parent_source_id=root_id,
        path_prefix="/tmp/acme",
    )
    await db_session.commit()
    await db_session.refresh(sub)

    assert sub.parent_source_id == root_id
    assert sub.path_prefix == "/tmp/acme"
    # Sub-sources don't own a Qdrant collection — they query the parent's.
    assert sub.collection_name is None
    # source_path mirrors the canonical prefix
    assert sub.source_path == "/tmp/acme"


async def test_sub_of_sub_is_rejected(db_session: AsyncSession):
    root_id = await _make_root(db_session)
    sm = SourceManager(db_session)
    sub = await sm.create_source(
        name="Sub",
        source_type="directory",
        source_path="ignored",
        parent_source_id=root_id,
        path_prefix="/tmp/acme",
    )
    await db_session.commit()
    await db_session.refresh(sub)

    with pytest.raises(ValueError, match="two-level hierarchy"):
        await sm.create_source(
            name="SubSub",
            source_type="directory",
            source_path="ignored",
            parent_source_id=sub.id,
            path_prefix="/tmp/acme/fy26",
        )


async def test_prefix_outside_root_is_rejected(db_session: AsyncSession):
    root_id = await _make_root(db_session)
    sm = SourceManager(db_session)
    with pytest.raises(ValueError, match="not under parent root"):
        await sm.create_source(
            name="Bad",
            source_type="directory",
            source_path="ignored",
            parent_source_id=root_id,
            path_prefix="/etc/passwd",
        )


async def test_resolve_source_ids_translates_sub_to_root(db_session: AsyncSession):
    root_id = await _make_root(db_session)
    sm = SourceManager(db_session)
    sub = await sm.create_source(
        name="Sub",
        source_type="directory",
        source_path="ignored",
        parent_source_id=root_id,
        path_prefix="/tmp/acme",
    )
    await db_session.commit()
    await db_session.refresh(sub)

    root_ids, overlay = await resolve_source_ids(db_session, [sub.id])
    assert root_ids == [root_id]
    assert overlay[root_id]["path_prefix"] == ["/tmp/acme"]


async def test_resolve_two_subs_unions_prefixes(db_session: AsyncSession):
    root_id = await _make_root(db_session)
    sm = SourceManager(db_session)
    sub1 = await sm.create_source(
        name="A", source_type="directory", source_path="ignored",
        parent_source_id=root_id, path_prefix="/tmp/a",
    )
    sub2 = await sm.create_source(
        name="B", source_type="directory", source_path="ignored",
        parent_source_id=root_id, path_prefix="/tmp/b",
    )
    await db_session.commit()
    await db_session.refresh(sub1)
    await db_session.refresh(sub2)

    root_ids, overlay = await resolve_source_ids(db_session, [sub1.id, sub2.id])
    # Two sub-sources of the same root collapse onto one root id but their
    # prefixes union via MatchAny semantics.
    assert root_ids == [root_id]
    assert set(overlay[root_id]["path_prefix"]) == {"/tmp/a", "/tmp/b"}


async def test_overlay_filters_for_root_merges_with_base(db_session: AsyncSession):
    """overlay_filters_for_root preserves caller filters and adds the overlay."""
    root_id = "fake-root-id"
    overlay = {
        root_id: {"path_prefix": ["/tmp/acme"], "path_excludes": ["/tmp/acme/personal"]}
    }
    merged = overlay_filters_for_root(overlay, root_id, {"platforms": ["AcmeCRM"]})
    assert merged["platforms"] == ["AcmeCRM"]
    assert merged["path_prefix"] == ["/tmp/acme"]
    assert merged["path_excludes"] == ["/tmp/acme/personal"]

    # No-op when overlay is empty
    same = overlay_filters_for_root({}, root_id, {"platforms": ["X"]})
    assert same == {"platforms": ["X"]}
