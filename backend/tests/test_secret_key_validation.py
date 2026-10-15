"""Tests for SECRET_KEY startup validation (#35)."""
import pytest

from app.core.secret_key import (
    INSECURE_SECRET_KEYS,
    InsecureSecretKeyError,
    validate_secret_key,
)


def test_empty_local_generates_ephemeral():
    key = validate_secret_key("", external_hostname=None)
    assert key
    assert key not in INSECURE_SECRET_KEYS


def test_empty_exposed_raises():
    with pytest.raises(InsecureSecretKeyError, match="SECRET_KEY is not set"):
        validate_secret_key("", external_hostname="api.example.com")


def test_insecure_exposed_raises():
    bad = next(iter(INSECURE_SECRET_KEYS))
    with pytest.raises(InsecureSecretKeyError, match="known default"):
        validate_secret_key(bad, external_hostname="api.example.com")


def test_insecure_local_allowed():
    bad = next(iter(INSECURE_SECRET_KEYS))
    assert validate_secret_key(bad, external_hostname=None) == bad


def test_strong_key_preserved():
    key = "a" * 64
    assert validate_secret_key(key, external_hostname="api.example.com") == key
