"""
Regression tests for the source-delete cascade hang.

Root cause: ``Source``'s child relationships declared ``cascade="all,
delete-orphan"`` without ``passive_deletes=True``. Deleting a source therefore
made SQLAlchemy eagerly load the entire child graph into memory to delete it
row-by-row. A directory source with millions of ``watcher_events`` froze the
backend's event loop (loading 3.3M rows) and the delete never committed.

Fix: every child FK already declares ``ON DELETE CASCADE``, so
``passive_deletes=True`` lets Postgres do the cascade server-side and SQLAlchemy
issues a single ``DELETE FROM sources``.

Two guards:
  * structural — assert ``passive_deletes`` stays set on each relationship, so
    the fix can't be silently removed.
  * behavioral — with FK enforcement on (as Postgres always has), deleting a
    source with many children cascades them and orphans nothing.
"""
from unittest.mock import MagicMock

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models import DocumentContent, IndexingLog, Source, WatcherEvent
from app.services.ingestion.source_manager import SourceManager
from tests.factories import KnowledgeSourceFactory


# Child relationships that must rely on DB-level ON DELETE CASCADE.
_PASSIVE_DELETE_RELS = [
    "library_bindings",
    "indexing_logs",
    "project_assignments",
    "agent_bindings",
    "scraped_contents",
    "watcher_events",
    "sub_sources",
]


def test_source_child_relationships_use_passive_deletes():
    """Every cascade child of Source must use passive_deletes=True.

    Without it, deleting a source eagerly loads the full child graph — the
    cause of the millions-of-watcher_events freeze.
    """
    rels = Source.__mapper__.relationships
    for name in _PASSIVE_DELETE_RELS:
        assert rels[name].passive_deletes is True, (
            f"Source.{name} must set passive_deletes=True so deletes cascade "
            f"in the database instead of loading every child row into memory."
        )


@pytest.fixture
async def fk_session():
    """Isolated in-memory SQLite session with foreign keys enforced.

    The shared test fixture leaves SQLite FK enforcement off, so DB-level
    ON DELETE CASCADE never fires there. This fixture turns it on (StaticPool
    keeps the single in-memory connection alive) so cascade behaviour matches
    Postgres.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


async def _count(session, model, source_id) -> int:
    result = await session.execute(
        select(func.count()).select_from(model).where(model.source_id == source_id)
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_delete_source_cascades_children_in_db(fk_session):
    """Deleting a source with many children removes them via DB cascade."""
    source = KnowledgeSourceFactory.create(
        name="Work Documents",
        source_type="directory",
        source_path="/data/documents",
        collection_name="source_own_coll",
    )
    fk_session.add(source)
    await fk_session.flush()

    # A directory source accumulates watcher events plus content/log rows.
    for i in range(50):
        fk_session.add(WatcherEvent(
            id=f"evt-{i}", source_id=source.id, event_type="modified",
            file_path=f"/data/documents/f{i}.md", severity="info",
        ))
    for i in range(5):
        fk_session.add(DocumentContent(
            id=f"doc-{i}", source_id=source.id, url=f"/data/documents/f{i}.md",
            raw_content="x", content_hash=f"h{i}",
        ))
    fk_session.add(IndexingLog(source_id=source.id, url="/data/documents/f0.md"))
    await fk_session.commit()

    assert await _count(fk_session, WatcherEvent, source.id) == 50

    mgr = SourceManager(fk_session)
    mgr.client = MagicMock()  # don't touch Qdrant

    assert await mgr.delete_source(source.id) is True
    await fk_session.commit()

    # Parent gone, and nothing orphaned.
    assert await mgr.get_source(source.id) is None
    assert await _count(fk_session, WatcherEvent, source.id) == 0
    assert await _count(fk_session, DocumentContent, source.id) == 0
    assert await _count(fk_session, IndexingLog, source.id) == 0


@pytest.mark.asyncio
async def test_delete_source_does_not_preload_watcher_events(fk_session):
    """delete_source must not SELECT child rows to cascade them.

    Deterministic guard for the original bug: without passive_deletes,
    SQLAlchemy emits ``SELECT ... FROM watcher_events`` to load the children
    before deleting them — exactly the load that froze on 3.3M rows. With the
    fix the cascade is left to the database, so no such SELECT is issued.
    """
    source = KnowledgeSourceFactory.create(
        name="Big", source_type="directory", source_path="/data/documents",
        collection_name="c",
    )
    fk_session.add(source)
    await fk_session.flush()
    for i in range(100):
        fk_session.add(WatcherEvent(
            id=f"e-{i}", source_id=source.id, event_type="modified", severity="info",
        ))
    await fk_session.commit()

    statements: list[str] = []
    sync_engine = fk_session.bind.sync_engine

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)

    try:
        mgr = SourceManager(fk_session)
        mgr.client = MagicMock()
        await mgr.delete_source(source.id)
        await fk_session.commit()
    finally:
        event.remove(sync_engine, "before_cursor_execute", _capture)

    watcher_selects = [
        s for s in statements
        if s.lstrip().lower().startswith("select") and "watcher_events" in s.lower()
    ]
    assert watcher_selects == [], (
        f"delete_source eagerly queried watcher_events (passive_deletes "
        f"regression): {watcher_selects}"
    )
