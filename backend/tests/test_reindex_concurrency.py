"""
Test that per-file re-index fan-out is concurrency-bounded.

force_sync and the watcher poll loop dispatch reindex_file via
asyncio.create_task with no caller-side limit. Without a global cap they each
open a DB session and exhaust the connection pool. reindex_file must gate on a
semaphore so no more than REINDEX_MAX_CONCURRENCY run their work at once.
"""

import asyncio
from unittest.mock import patch

import pytest

from app.services.ingestion import background_tasks
from app.services.ingestion.background_tasks import (
    REINDEX_MAX_CONCURRENCY,
    reindex_file,
)


@pytest.mark.asyncio
async def test_reindex_file_caps_concurrency():
    active = 0
    peak = 0

    async def fake_inner(source_id, file_path):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)  # hold the slot so overlap is observable
        active -= 1

    with patch.object(background_tasks, "_reindex_file_inner", fake_inner):
        await asyncio.gather(*[reindex_file("s", f"/f/{i}") for i in range(50)])

    assert peak <= REINDEX_MAX_CONCURRENCY
    assert peak > 0  # work actually ran
