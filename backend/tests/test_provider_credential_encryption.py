"""
Tests for provider API-key encryption at rest.

Provider keys live in `provider_configs.api_key_encrypted`. Historically the
column held PLAINTEXT despite its name. These tests pin the wiring that
encrypts keys at the write sites and transparently decrypts at the read sites,
while tolerating legacy plaintext rows that predate the change.
"""
import pytest
from cryptography.fernet import Fernet

from app.core.encryption import (
    decrypt_credential,
    decrypt_if_encrypted,
    encrypt_credential,
    is_encrypted,
)
from app.services.provider_service import ProviderService


def test_decrypt_if_encrypted_passes_plaintext_through():
    """Legacy plaintext rows must be returned unchanged (no gAAAAA prefix)."""
    assert decrypt_if_encrypted("sk-legacy-plaintext") == "sk-legacy-plaintext"


def test_decrypt_if_encrypted_round_trips_ciphertext():
    """An encrypted value is detected and decrypted back to the original."""
    ciphertext = encrypt_credential("sk-secret-123")
    assert is_encrypted(ciphertext)
    assert decrypt_if_encrypted(ciphertext) == "sk-secret-123"


@pytest.mark.parametrize("empty", [None, ""])
def test_decrypt_if_encrypted_handles_empty(empty):
    """None / empty values pass through without attempting decryption."""
    assert decrypt_if_encrypted(empty) == empty


def test_decrypt_if_encrypted_falls_back_when_decryption_fails():
    """An undecryptable token (e.g. encrypted under a rotated key) must not
    crash the boot-critical read path; the raw stored value is returned."""
    # Valid gAAAAA-format token, but produced under a *different* key.
    foreign_token = Fernet(Fernet.generate_key()).encrypt(b"sk-secret").decode()
    assert is_encrypted(foreign_token)
    assert decrypt_if_encrypted(foreign_token) == foreign_token


async def test_update_provider_config_encrypts_api_key_at_rest(db_session):
    """The service write path stores ciphertext, not the raw key."""
    service = ProviderService(db_session)

    config = await service.update_provider_config("openai", api_key="sk-secret-123")

    # The column must NOT contain the plaintext key.
    assert config.api_key_encrypted != "sk-secret-123"
    assert is_encrypted(config.api_key_encrypted)
    # And the read path recovers the original value.
    assert decrypt_if_encrypted(config.api_key_encrypted) == "sk-secret-123"
    assert decrypt_credential(config.api_key_encrypted) == "sk-secret-123"
