"""
Regression test for the startup migration resilience guard.

Background: the backend runs `alembic upgrade head` during application startup
(_run_alembic_migrations). On 2026-06-22 a git branch switch on the live,
volume-mounted dev checkout left the shared database stamped at a migration
revision (f8b9c0d1e2a3, the experiments table) that the newly checked-out
branch did not yet contain. `alembic upgrade head` could not resolve the DB's
current revision against the local script tree and raised CommandError, which
crashed application startup. Combined with uvicorn --reload (whose reloader
parent keeps the listening socket open while the worker is dead) this produced
a ~10h silent outage: the /mcp surface accepted TCP connections but never
completed a handshake, so callers hit their timeout and saw zero tools.

A database that is *ahead* of the code is safe to run against (the extra
tables/columns are simply ignored), so _run_alembic_migrations now logs a
warning and continues for that specific "unresolved revision" case, while
re-raising every other migration failure so genuine schema problems still
abort startup.
"""

import alembic.command
import pytest
from alembic.util.exc import CommandError
from alembic.script.revision import ResolutionError

from app.main import _run_alembic_migrations


def _raise_unresolved(cfg, rev):
    """Mimic alembic's `raise CommandError(...) from ResolutionError(...)`."""
    try:
        raise ResolutionError("No such revision or branch 'deadbeef'", "deadbeef")
    except ResolutionError as re:
        raise CommandError("Can't locate revision identified by 'deadbeef'") from re


def test_db_ahead_of_code_does_not_crash_startup(monkeypatch):
    """An unresolved DB revision (DB ahead of code) is tolerated, not fatal."""
    monkeypatch.setattr(alembic.command, "upgrade", _raise_unresolved)
    # Must not raise — startup continues despite the DB being ahead of the code.
    _run_alembic_migrations()


def test_genuine_migration_failure_still_propagates(monkeypatch):
    """Any non-resolution migration error must still abort startup."""

    def _raise_other(cfg, rev):
        raise CommandError("genuine migration failure: column already exists")

    monkeypatch.setattr(alembic.command, "upgrade", _raise_other)
    with pytest.raises(CommandError):
        _run_alembic_migrations()
