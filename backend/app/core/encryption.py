"""
Encryption utilities for securing sensitive data at rest.

Uses Fernet symmetric encryption derived from the application secret key.
"""
import base64
import hashlib
from typing import Optional

import structlog
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

logger = structlog.get_logger()


def _get_fernet() -> Fernet:
    """
    Get Fernet instance using app secret key.

    Derives a 32-byte key from secret_key using SHA256,
    then base64 encodes for Fernet compatibility.
    """
    settings = get_settings()
    # Derive 32-byte key from secret_key using SHA256
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    # Fernet requires url-safe base64 encoded 32-byte key
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_credential(plaintext: str) -> str:
    """
    Encrypt a credential string for secure storage.

    Args:
        plaintext: The sensitive value to encrypt

    Returns:
        Base64-encoded encrypted string safe for database storage
    """
    if not plaintext:
        return ""
    fernet = _get_fernet()
    return fernet.encrypt(plaintext.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    """
    Decrypt a stored credential.

    Args:
        ciphertext: The encrypted value from the database

    Returns:
        The original plaintext value

    Raises:
        ValueError: If decryption fails (invalid key or corrupted data)
    """
    if not ciphertext:
        return ""
    try:
        fernet = _get_fernet()
        return fernet.decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Failed to decrypt credential - invalid key or corrupted data") from e


def mask_credential(value: str, visible_chars: int = 4) -> str:
    """
    Mask a credential for display, showing only last N characters.

    Args:
        value: The credential to mask
        visible_chars: Number of trailing characters to show

    Returns:
        Masked string like "********cdef"
    """
    if not value or len(value) <= visible_chars:
        return "********"
    return "*" * 8 + value[-visible_chars:]


def is_encrypted(value: Optional[str]) -> bool:
    """
    Check if a value appears to be Fernet-encrypted.

    Fernet tokens start with 'gAAAAA' when base64 encoded.
    """
    if not value:
        return False
    return value.startswith("gAAAAA")


def decrypt_if_encrypted(value: Optional[str]) -> Optional[str]:
    """
    Decrypt a stored credential only if it is Fernet-encrypted.

    The ``provider_configs.api_key_encrypted`` column may contain a mix of
    legacy plaintext rows (written before encryption was wired in) and
    encrypted rows. Read sites use this helper so they can consume the column
    without knowing which form a given row is in: encrypted values are
    decrypted, plaintext / empty / None values are returned unchanged.
    """
    if not value:
        return value
    if is_encrypted(value):
        try:
            return decrypt_credential(value)
        except ValueError:
            # An undecryptable token (e.g. encrypted under a SECRET_KEY that has
            # since been rotated) must not crash a boot-critical read path. Fall
            # back to the raw value and let the provider call fail its own auth
            # rather than taking down startup.
            logger.warning(
                "Failed to decrypt stored credential; using raw value. "
                "Has SECRET_KEY changed since this credential was stored?"
            )
            return value
    return value
