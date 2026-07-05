"""
Tests for agent API key validation (#184).

Covers the indexed key-prefix lookup, the legacy NULL-prefix fallback with
opportunistic backfill, and off-loop Argon2 verification.
"""
import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.agent_service as agent_service_module
from app.services.agent_service import (
    API_KEY_PREFIX_LENGTH,
    AgentService,
    _hash_agent_key,
    _verify_agent_key,
)
from app.services.auth_service import AuthService
from tests.factories import AgentFactory


async def _create_public_agent_with_key(
    db_session: AsyncSession, service: AgentService, name: str
) -> tuple[str, str]:
    """Create a public agent with a generated API key.

    Returns (agent primary key id, plain API key).
    """
    agent = await service.create_agent(
        name=name,
        system_prompt="You are a helpful test assistant.",
        model_provider="openai",
        model_name="gpt-4",
    )
    plain_key = await service.set_api_key(agent.id)
    assert plain_key is not None
    return agent.id, plain_key


class _VerifySpy:
    """Counting wrapper around _verify_agent_key."""

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, stored_hash: str, plain_key: str) -> tuple[bool, bool]:
        self.calls.append(stored_hash)
        return _verify_agent_key(stored_hash, plain_key)


class TestKeyPrefixStoredOnCreation:
    """New keys always store the indexed prefix."""

    @pytest.mark.asyncio
    async def test_set_api_key_stores_prefix(self, db_session: AsyncSession):
        service = AgentService(db_session)
        agent_id, plain_key = await _create_public_agent_with_key(
            db_session, service, "Prefix Agent"
        )

        agent = await service.get_agent(agent_id)
        assert agent.api_key_prefix == plain_key[:API_KEY_PREFIX_LENGTH]
        assert plain_key.startswith("as_")

    @pytest.mark.asyncio
    async def test_revoke_api_key_clears_prefix(self, db_session: AsyncSession):
        service = AgentService(db_session)
        agent_id, _ = await _create_public_agent_with_key(
            db_session, service, "Revoke Agent"
        )

        assert await service.revoke_api_key(agent_id) is True

        agent = await service.get_agent(agent_id)
        assert agent.api_key_hash is None
        assert agent.api_key_prefix is None


class TestPrefixNarrowsCandidates:
    """Invalid keys must not trigger one Argon2 hash per agent."""

    @pytest.mark.asyncio
    async def test_invalid_key_no_prefix_match_hashes_nothing(
        self, db_session: AsyncSession, monkeypatch
    ):
        service = AgentService(db_session)
        for i in range(5):
            await _create_public_agent_with_key(db_session, service, f"Agent {i}")

        spy = _VerifySpy()
        monkeypatch.setattr(agent_service_module, "_verify_agent_key", spy)

        # No stored prefix matches and no NULL-prefix legacy rows exist,
        # so zero verifications should run.
        result = await service.validate_api_key("as_completely-invalid-key-000000")
        assert result is None
        assert len(spy.calls) == 0

    @pytest.mark.asyncio
    async def test_invalid_key_with_prefix_match_hashes_one_candidate(
        self, db_session: AsyncSession, monkeypatch
    ):
        service = AgentService(db_session)
        keys = []
        for i in range(5):
            _, plain_key = await _create_public_agent_with_key(
                db_session, service, f"Agent {i}"
            )
            keys.append(plain_key)

        spy = _VerifySpy()
        monkeypatch.setattr(agent_service_module, "_verify_agent_key", spy)

        # Same prefix as agent 0's key but a wrong remainder: exactly the
        # one prefix-matched candidate gets an Argon2 verification.
        forged = keys[0][:API_KEY_PREFIX_LENGTH] + "X" * 31
        result = await service.validate_api_key(forged)
        assert result is None
        assert len(spy.calls) == 1

    @pytest.mark.asyncio
    async def test_valid_key_validates_via_prefix_lookup(
        self, db_session: AsyncSession, monkeypatch
    ):
        service = AgentService(db_session)
        agent_ids = []
        keys = []
        for i in range(3):
            agent_id, plain_key = await _create_public_agent_with_key(
                db_session, service, f"Agent {i}"
            )
            agent_ids.append(agent_id)
            keys.append(plain_key)

        spy = _VerifySpy()
        monkeypatch.setattr(agent_service_module, "_verify_agent_key", spy)

        result = await service.validate_api_key(keys[1])
        assert result is not None
        assert result.id == agent_ids[1]
        assert len(spy.calls) == 1


class TestLegacyNullPrefixFallback:
    """Keys issued before the prefix column keep working and get backfilled."""

    @pytest.mark.asyncio
    async def test_legacy_row_validates_and_backfills_prefix(
        self, db_session: AsyncSession
    ):
        plain_key = "as_legacy-key-with-no-stored-prefix-0123456789"
        agent = AgentFactory.create(name="Legacy Agent", is_public=True)
        agent.api_key_hash = _hash_agent_key(plain_key)
        agent.api_key_prefix = None
        db_session.add(agent)
        await db_session.commit()

        service = AgentService(db_session)
        result = await service.validate_api_key(plain_key)

        assert result is not None
        assert result.id == agent.id
        # Prefix backfilled on successful validation
        assert result.api_key_prefix == plain_key[:API_KEY_PREFIX_LENGTH]

        # Second validation now resolves via the indexed prefix path
        result2 = await service.validate_api_key(plain_key)
        assert result2 is not None
        assert result2.id == agent.id

    @pytest.mark.asyncio
    async def test_legacy_sha256_hash_upgraded_and_prefix_backfilled(
        self, db_session: AsyncSession
    ):
        import hashlib

        plain_key = "as_legacy-sha256-key-for-upgrade-test-0123456"
        agent = AgentFactory.create(name="SHA Agent", is_public=True)
        agent.api_key_hash = hashlib.sha256(plain_key.encode()).hexdigest()
        agent.api_key_prefix = None
        db_session.add(agent)
        await db_session.commit()

        service = AgentService(db_session)
        result = await service.validate_api_key(plain_key)

        assert result is not None
        assert result.api_key_hash.startswith("$argon2")
        assert result.api_key_prefix == plain_key[:API_KEY_PREFIX_LENGTH]

    @pytest.mark.asyncio
    async def test_invalid_key_returns_none_with_legacy_rows_present(
        self, db_session: AsyncSession
    ):
        agent = AgentFactory.create(name="Legacy Agent", is_public=True)
        agent.api_key_hash = _hash_agent_key("as_some-legacy-key-value-here")
        agent.api_key_prefix = None
        db_session.add(agent)
        await db_session.commit()

        service = AgentService(db_session)
        result = await service.validate_api_key("as_totally-wrong-key-value-here")
        assert result is None


class TestVerificationRunsOffLoop:
    """Argon2 verification goes through asyncio.to_thread."""

    @pytest.mark.asyncio
    async def test_agent_validation_uses_to_thread(
        self, db_session: AsyncSession, monkeypatch
    ):
        service = AgentService(db_session)
        _, plain_key = await _create_public_agent_with_key(
            db_session, service, "Thread Agent"
        )

        original_to_thread = asyncio.to_thread
        called_fns = []

        async def spy_to_thread(fn, *args, **kwargs):
            called_fns.append(getattr(fn, "__name__", repr(fn)))
            return await original_to_thread(fn, *args, **kwargs)

        monkeypatch.setattr(
            agent_service_module.asyncio, "to_thread", spy_to_thread
        )

        result = await service.validate_api_key(plain_key)
        assert result is not None
        assert "_verify_agent_key" in called_fns


class TestPlatformKeyValidation:
    """Platform APIKey path: prefix lookup intact, verification off-loop."""

    @pytest.mark.asyncio
    async def test_platform_key_validates(self, db_session: AsyncSession):
        service = AuthService(db_session)
        api_key, plain_key = await service.create_key(
            name="ACME test key", scopes=["read"]
        )
        assert api_key.key_prefix == plain_key[:8]

        result = await service.validate_key(plain_key)
        assert result is not None
        assert result.id == api_key.id

    @pytest.mark.asyncio
    async def test_platform_invalid_key_returns_none(
        self, db_session: AsyncSession
    ):
        service = AuthService(db_session)
        await service.create_key(name="ACME test key", scopes=["read"])

        result = await service.validate_key("pk_invalid-key-value")
        assert result is None
