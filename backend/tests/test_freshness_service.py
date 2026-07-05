"""
Tests for freshness lifecycle service.
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from app.services.freshness_service import (
    get_freshness_status,
    compute_next_refresh_at,
    STATUS_CURRENT,
    STATUS_AGING,
    STATUS_STALE,
)


def _make_source(**kwargs):
    """Create a mock Source with freshness fields."""
    source = MagicMock()
    source.freshness_policy = kwargs.get("freshness_policy", "none")
    source.stale_after_days = kwargs.get("stale_after_days", None)
    source.refresh_interval_days = kwargs.get("refresh_interval_days", None)
    source.last_indexed = kwargs.get("last_indexed", None)
    source.next_refresh_at = kwargs.get("next_refresh_at", None)
    return source


class TestGetFreshnessStatus:
    """Tests for get_freshness_status()."""

    def test_none_policy_always_current(self):
        source = _make_source(freshness_policy="none")
        assert get_freshness_status(source) == STATUS_CURRENT

    def test_none_policy_with_stale_days_still_current(self):
        source = _make_source(
            freshness_policy="none",
            stale_after_days=30,
            last_indexed=datetime.utcnow() - timedelta(days=60),
        )
        assert get_freshness_status(source) == STATUS_CURRENT

    def test_no_stale_after_days_always_current(self):
        source = _make_source(freshness_policy="automatic")
        assert get_freshness_status(source) == STATUS_CURRENT

    def test_never_indexed_is_stale(self):
        source = _make_source(
            freshness_policy="automatic",
            stale_after_days=30,
            last_indexed=None,
        )
        assert get_freshness_status(source) == STATUS_STALE

    def test_recently_indexed_is_current(self):
        source = _make_source(
            freshness_policy="automatic",
            stale_after_days=30,
            last_indexed=datetime.utcnow() - timedelta(days=5),
        )
        assert get_freshness_status(source) == STATUS_CURRENT

    def test_aging_at_80_percent(self):
        # 80% of 30 days = 24 days
        source = _make_source(
            freshness_policy="automatic",
            stale_after_days=30,
            last_indexed=datetime.utcnow() - timedelta(days=25),
        )
        assert get_freshness_status(source) == STATUS_AGING

    def test_stale_past_threshold(self):
        source = _make_source(
            freshness_policy="manual",
            stale_after_days=30,
            last_indexed=datetime.utcnow() - timedelta(days=35),
        )
        assert get_freshness_status(source) == STATUS_STALE

    def test_exactly_at_threshold_is_stale(self):
        source = _make_source(
            freshness_policy="automatic",
            stale_after_days=30,
            last_indexed=datetime.utcnow() - timedelta(days=30),
        )
        assert get_freshness_status(source) == STATUS_STALE

    def test_manual_policy_uses_same_logic(self):
        source = _make_source(
            freshness_policy="manual",
            stale_after_days=90,
            last_indexed=datetime.utcnow() - timedelta(days=10),
        )
        assert get_freshness_status(source) == STATUS_CURRENT

    def test_null_policy_treated_as_none(self):
        source = _make_source(freshness_policy=None)
        assert get_freshness_status(source) == STATUS_CURRENT


class TestComputeNextRefreshAt:
    """Tests for compute_next_refresh_at()."""

    def test_automatic_with_interval(self):
        last = datetime(2026, 4, 1, 12, 0, 0)
        source = _make_source(
            freshness_policy="automatic",
            refresh_interval_days=30,
            last_indexed=last,
        )
        result = compute_next_refresh_at(source)
        assert result == last + timedelta(days=30)

    def test_none_policy_returns_none(self):
        source = _make_source(freshness_policy="none", refresh_interval_days=30)
        assert compute_next_refresh_at(source) is None

    def test_manual_policy_returns_none(self):
        source = _make_source(
            freshness_policy="manual",
            refresh_interval_days=30,
            last_indexed=datetime.utcnow(),
        )
        assert compute_next_refresh_at(source) is None

    def test_no_interval_returns_none(self):
        source = _make_source(
            freshness_policy="automatic",
            refresh_interval_days=None,
            last_indexed=datetime.utcnow(),
        )
        assert compute_next_refresh_at(source) is None

    def test_no_last_indexed_returns_none(self):
        source = _make_source(
            freshness_policy="automatic",
            refresh_interval_days=30,
            last_indexed=None,
        )
        assert compute_next_refresh_at(source) is None
