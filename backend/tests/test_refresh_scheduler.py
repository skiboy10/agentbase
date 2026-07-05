"""
Tests for the refresh scheduler.
"""
import os
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"


class TestCheckAndEnqueueRefreshes:
    """Tests for _check_and_enqueue_refreshes()."""

    @pytest.mark.asyncio
    @patch("app.services.refresh_scheduler.async_session_maker")
    async def test_no_due_sources_returns_zero(self, mock_session_maker):
        from app.services.refresh_scheduler import _check_and_enqueue_refreshes

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result.scalars.return_value = mock_scalars
        mock_db.execute.return_value = mock_result

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_db
        mock_ctx.__aexit__.return_value = None
        mock_session_maker.return_value = mock_ctx

        count = await _check_and_enqueue_refreshes()
        assert count == 0

    @pytest.mark.asyncio
    @patch("app.services.refresh_scheduler.async_session_maker")
    async def test_due_source_gets_enqueued(self, mock_session_maker):
        from app.services.refresh_scheduler import _check_and_enqueue_refreshes

        # Create a mock due source
        source = MagicMock()
        source.id = "src-123"
        source.name = "Test Source"
        source.project_id = None
        source.freshness_policy = "automatic"
        source.next_refresh_at = datetime.utcnow() - timedelta(hours=1)
        source.status = "indexed"

        mock_db = AsyncMock()

        # First call: find due sources
        due_result = MagicMock()
        due_scalars = MagicMock()
        due_scalars.all.return_value = [source]
        due_result.scalars.return_value = due_scalars

        # Second call: check no existing job
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None

        mock_db.execute.side_effect = [due_result, existing_result]

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_db
        mock_ctx.__aexit__.return_value = None
        mock_session_maker.return_value = mock_ctx

        count = await _check_and_enqueue_refreshes()
        assert count == 1
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.services.refresh_scheduler.async_session_maker")
    async def test_skips_source_with_existing_job(self, mock_session_maker):
        from app.services.refresh_scheduler import _check_and_enqueue_refreshes

        source = MagicMock()
        source.id = "src-456"
        source.name = "Already Queued"
        source.project_id = None
        source.freshness_policy = "automatic"
        source.next_refresh_at = datetime.utcnow() - timedelta(hours=1)
        source.status = "indexed"

        mock_db = AsyncMock()

        # First call: find due sources
        due_result = MagicMock()
        due_scalars = MagicMock()
        due_scalars.all.return_value = [source]
        due_result.scalars.return_value = due_scalars

        # Second call: existing job found
        existing_job = MagicMock()
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_job

        mock_db.execute.side_effect = [due_result, existing_result]

        mock_ctx = AsyncMock()
        mock_ctx.__aenter__.return_value = mock_db
        mock_ctx.__aexit__.return_value = None
        mock_session_maker.return_value = mock_ctx

        count = await _check_and_enqueue_refreshes()
        assert count == 0
