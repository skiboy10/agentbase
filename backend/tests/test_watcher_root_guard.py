"""
Tests for the watcher root-health guard.

Covers the two protections that stop a broken/unmounted watch root from being
misread as "every file was deleted":

  1. _probe_root_health_sync  - classify a root as ok / missing / unreadable
  2. _is_mass_deletion        - flag a single reconcile cycle that would wipe
                                 >=90% of the indexed set (min 50 files)

Also asserts force_sync refuses to run against an unhealthy root rather than
issuing mass deletions.

Background: a Docker bind mount whose host source is renamed leaves an empty
but present mountpoint. Path.is_dir() still returns True, so the old code
scanned it as empty and treated all indexed files as deletions.
"""

import os

import pytest

from app.services.ingestion.watcher import (
    WATCH_ROOT_MASS_DELETE_FRACTION,
    WATCH_ROOT_MASS_DELETE_MIN,
    WatcherManager,
    _is_mass_deletion,
    _probe_root_health_sync,
)
from pathlib import Path

from tests.factories import KnowledgeSourceFactory


# ---------------------------------------------------------------------------
# _probe_root_health_sync
# ---------------------------------------------------------------------------

def test_probe_healthy_directory(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    status, detail = _probe_root_health_sync(tmp_path)
    assert status == "ok"
    assert detail is None


def test_probe_empty_directory_is_ok(tmp_path):
    # An empty-but-readable directory is healthy; emptiness alone is NOT
    # "unreadable". The mass-deletion valve is what guards a sudden wipe.
    status, detail = _probe_root_health_sync(tmp_path)
    assert status == "ok"


def test_probe_missing_path(tmp_path):
    status, detail = _probe_root_health_sync(tmp_path / "does-not-exist")
    assert status == "missing"
    assert "does not exist" in detail


def test_probe_path_is_a_file(tmp_path):
    f = tmp_path / "not-a-dir.txt"
    f.write_text("x")
    status, detail = _probe_root_health_sync(f)
    assert status == "unreadable"
    assert "not a directory" in detail


# ---------------------------------------------------------------------------
# _is_mass_deletion
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "indexed,deleted,expected",
    [
        (2512, 2377, True),    # the real incident: ~95% vanished
        (2512, 2512, True),    # whole tree gone
        (2512, 100, False),    # normal churn
        (100, 90, True),       # exactly 90%
        (100, 89, False),      # just under 90%
        (50, 50, True),        # at the minimum-size floor
        (49, 49, False),       # below the floor: too small to guard
        (10, 10, False),       # tiny index, ignore
        (0, 0, False),         # empty index, nothing to protect
    ],
)
def test_is_mass_deletion(indexed, deleted, expected):
    assert _is_mass_deletion(indexed, deleted) is expected


def test_mass_deletion_constants_are_sane():
    assert 0 < WATCH_ROOT_MASS_DELETE_FRACTION <= 1
    assert WATCH_ROOT_MASS_DELETE_MIN >= 1


# ---------------------------------------------------------------------------
# force_sync refuses to run against an unhealthy root
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_force_sync_raises_on_missing_root(db_session):
    source = KnowledgeSourceFactory.create(
        name="Mount Source",
        source_type="directory",
    )
    source.source_path = "/tmp/agentbase-does-not-exist-xyz"
    db_session.add(source)
    await db_session.commit()

    manager = WatcherManager()
    with pytest.raises(ValueError):
        await manager.force_sync(source.id, db_session)


@pytest.mark.asyncio
async def test_force_sync_raises_on_file_root(db_session, tmp_path):
    f = tmp_path / "a-file"
    f.write_text("x")

    source = KnowledgeSourceFactory.create(
        name="Mount Source",
        source_type="directory",
    )
    source.source_path = str(f)
    db_session.add(source)
    await db_session.commit()

    manager = WatcherManager()
    with pytest.raises(ValueError):
        await manager.force_sync(source.id, db_session)
