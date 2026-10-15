"""Tests for per-API-key rate_limit_rpm enforcement (#10)."""
from app.core.rate_limit import PerKeyRateLimiter


def test_unlimited_when_rpm_none():
    lim = PerKeyRateLimiter()
    for _ in range(100):
        allowed, retry = lim.check("key-a", None)
        assert allowed is True
        assert retry == 0


def test_unlimited_when_rpm_zero():
    lim = PerKeyRateLimiter()
    allowed, _ = lim.check("key-a", 0)
    assert allowed is True


def test_enforces_rpm_budget():
    lim = PerKeyRateLimiter()
    for _ in range(3):
        allowed, _ = lim.check("key-a", 3)
        assert allowed is True
    allowed, retry = lim.check("key-a", 3)
    assert allowed is False
    assert retry >= 1


def test_keys_are_isolated():
    lim = PerKeyRateLimiter()
    for _ in range(2):
        assert lim.check("key-a", 2)[0] is True
    assert lim.check("key-a", 2)[0] is False
    assert lim.check("key-b", 2)[0] is True


def test_reset_clears_buckets():
    lim = PerKeyRateLimiter()
    lim.check("key-a", 1)
    assert lim.check("key-a", 1)[0] is False
    lim.reset()
    assert lim.check("key-a", 1)[0] is True
