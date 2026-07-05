"""
Platform API key management service.

Handles creation, validation, revocation, and listing of platform-level API keys.
These are distinct from per-agent API keys (Agent.api_key_hash) which are used
for agent invocation auth only.
"""
import asyncio
import hashlib
import secrets
from datetime import datetime
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import APIKey

logger = structlog.get_logger()

# Valid scopes for platform API keys
VALID_SCOPES = {"read", "write", "admin"}

# Argon2 hasher — time_cost=2, memory_cost=65536 (64MB), parallelism=2 are
# OWASP-recommended minimums for interactive logins; fine for API keys too.
_ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)


def _hash_key(plain_key: str) -> str:
    """Hash a plain API key using Argon2id."""
    return _ph.hash(plain_key)


def _verify_key(stored_hash: str, plain_key: str) -> tuple[bool, bool]:
    """
    Verify a plain key against its stored hash.

    Returns a tuple of (is_valid, needs_rehash).
    - is_valid: True if the key matches.
    - needs_rehash: True if the stored hash used SHA-256 and should be
      transparently upgraded to Argon2 on the next successful login.
    """
    if stored_hash.startswith("$argon2"):
        # Modern Argon2 hash
        try:
            _ph.verify(stored_hash, plain_key)
            return True, _ph.check_needs_rehash(stored_hash)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False, False
    else:
        # Legacy SHA-256 hash (64-char hex) — fall back for backward compat
        legacy_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        if secrets.compare_digest(legacy_hash, stored_hash):
            # Valid; flag for transparent upgrade to Argon2
            return True, True
        return False, False


class AuthService:
    """Platform API key management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def generate_key() -> tuple[str, str, str]:
        """
        Generate a new platform API key.

        Returns:
            Tuple of (plain_key, key_hash, key_prefix).
            plain_key is shown to user once only.
            key_hash is an Argon2id hash (starts with '$argon2id$').
        """
        raw = secrets.token_urlsafe(32)
        plain_key = f"pk_{raw}"
        key_hash = _hash_key(plain_key)
        key_prefix = plain_key[:8]
        return plain_key, key_hash, key_prefix

    async def create_key(
        self,
        name: str,
        scopes: list[str],
        rate_limit_rpm: Optional[int] = None,
        expires_at: Optional[datetime] = None,
    ) -> tuple[APIKey, str]:
        """
        Create a new platform API key.

        Returns:
            Tuple of (APIKey model, plain_key).
            The plain_key is returned once and never stored.
        """
        # Validate scopes
        invalid = set(scopes) - VALID_SCOPES
        if invalid:
            raise ValueError(f"Invalid scopes: {invalid}. Valid: {VALID_SCOPES}")
        if not scopes:
            raise ValueError("At least one scope is required")

        plain_key, key_hash, key_prefix = self.generate_key()

        api_key = APIKey(
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scopes=scopes,
            rate_limit_rpm=rate_limit_rpm,
            expires_at=expires_at,
        )
        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)

        logger.info("Created platform API key", key_id=api_key.id, name=name, scopes=scopes)
        return api_key, plain_key

    async def validate_key(self, plain_key: str) -> Optional[APIKey]:
        """
        Validate a platform API key.

        Checks: hash match, is_active, not expired.
        Supports both Argon2id hashes (new keys) and SHA-256 hashes (legacy keys).
        On a successful SHA-256 match, the hash is transparently upgraded to Argon2.
        Updates last_used_at on success.

        Returns:
            The APIKey if valid, None otherwise.
        """
        # Argon2 hashes are not lookup-friendly — we must fetch by key_prefix
        # so we can verify each candidate in Python.  The prefix is always the
        # first 8 characters of the plain key (e.g. "pk_XXXXX"), which gives
        # us a selective index scan.
        key_prefix = plain_key[:8]
        stmt = select(APIKey).where(
            APIKey.key_prefix == key_prefix,
            APIKey.is_active == True,
        )
        result = await self.db.execute(stmt)
        candidates = result.scalars().all()

        api_key = None
        needs_rehash = False
        for candidate in candidates:
            # Argon2 verification is CPU-bound; run it off the event loop.
            is_valid, upgrade = await asyncio.to_thread(
                _verify_key, candidate.key_hash, plain_key
            )
            if is_valid:
                api_key = candidate
                needs_rehash = upgrade
                break

        if api_key is None:
            return None

        # Check expiration
        now = datetime.utcnow()
        if api_key.expires_at and api_key.expires_at < now:
            return None

        dirty = False

        # Transparent Argon2 upgrade for legacy SHA-256 keys
        if needs_rehash:
            api_key.key_hash = await asyncio.to_thread(_hash_key, plain_key)
            logger.info(
                "Upgraded API key hash from SHA-256 to Argon2",
                key_id=api_key.id,
                name=api_key.name,
            )
            dirty = True

        # Update last_used_at (throttled: only if >5 min since last update to reduce DB writes)
        if not api_key.last_used_at or (now - api_key.last_used_at).total_seconds() > 300:
            api_key.last_used_at = now
            dirty = True

        if dirty:
            await self.db.commit()

        return api_key

    async def validate_key_by_hash(self, key_hash: str) -> Optional[APIKey]:
        """
        Validate a platform API key by its pre-computed SHA-256 hash.

        This method exists only for backward compatibility with any code paths
        that pre-compute a SHA-256 hash before calling here.  New code should
        call validate_key(plain_key) directly; Argon2 hashes cannot be looked
        up this way.

        NOTE: The middleware no longer uses this path — it stores the fully
        validated APIKey object on request.state instead.  This method will
        only match legacy SHA-256 keys that have not yet been upgraded.
        """
        stmt = select(APIKey).where(
            APIKey.key_hash == key_hash,
            APIKey.is_active == True,
        )
        result = await self.db.execute(stmt)
        api_key = result.scalar_one_or_none()

        if api_key is None:
            return None

        now = datetime.utcnow()
        if api_key.expires_at and api_key.expires_at < now:
            return None

        if not api_key.last_used_at or (now - api_key.last_used_at).total_seconds() > 300:
            api_key.last_used_at = now
            await self.db.commit()

        return api_key

    async def list_keys(self) -> list[APIKey]:
        """List all API keys (active and revoked)."""
        stmt = select(APIKey).order_by(APIKey.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_key(self, key_id: str) -> Optional[APIKey]:
        """Get a single API key by ID."""
        stmt = select(APIKey).where(APIKey.id == key_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_key(self, key_id: str) -> bool:
        """
        Soft-revoke an API key by setting is_active = False.

        Returns:
            True if key was found and revoked, False if not found.
        """
        api_key = await self.get_key(key_id)
        if not api_key:
            return False

        api_key.is_active = False
        await self.db.commit()

        logger.info("Revoked platform API key", key_id=key_id, name=api_key.name)
        return True

    async def has_any_active_keys(self) -> bool:
        """
        Check if any active platform API keys exist.

        Used for bootstrap mode: when no keys exist, the platform
        operates in open mode for local requests.
        """
        stmt = select(sa_func.count()).select_from(APIKey).where(APIKey.is_active == True)
        result = await self.db.execute(stmt)
        count = result.scalar()
        return count > 0
