"""
SECRET_KEY validation for startup.

Local/dev may boot with an ephemeral key. Any externally exposed instance
(EXTERNAL_HOSTNAME set) must have a durable, non-default SECRET_KEY (#35).
"""
from __future__ import annotations

import secrets
from typing import Optional

# Known insecure placeholders historically shipped in examples / docs.
INSECURE_SECRET_KEYS = frozenset({
    "changeme-in-production",
    "changeme-generate-a-real-secret-key",
})


class InsecureSecretKeyError(RuntimeError):
    """Raised when SECRET_KEY is missing/insecure while the app is externally exposed."""


def validate_secret_key(
    secret_key: Optional[str],
    *,
    external_hostname: Optional[str],
) -> str:
    """
    Return a usable SECRET_KEY, or raise if the deployment is unsafe.

    - Empty + no EXTERNAL_HOSTNAME → generate ephemeral key (caller should log).
    - Empty or known-insecure + EXTERNAL_HOSTNAME → raise InsecureSecretKeyError.
    - Known-insecure without EXTERNAL_HOSTNAME → return as-is (caller may warn).
    """
    key = (secret_key or "").strip()
    exposed = bool(external_hostname and external_hostname.strip())

    if not key:
        if exposed:
            raise InsecureSecretKeyError(
                "SECRET_KEY is not set but EXTERNAL_HOSTNAME is configured. "
                "Refusing to start an externally reachable instance with an "
                "ephemeral key. Set a durable SECRET_KEY in .env "
                "(e.g. openssl rand -hex 32)."
            )
        return secrets.token_urlsafe(32)

    if key in INSECURE_SECRET_KEYS:
        if exposed:
            raise InsecureSecretKeyError(
                "SECRET_KEY is a known default and EXTERNAL_HOSTNAME is set. "
                "API keys and encrypted credentials are at risk. "
                "Set a unique SECRET_KEY in .env before exposing this instance. "
                "Generate one with: openssl rand -hex 32"
            )
        return key

    return key
