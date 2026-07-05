"""
Tests for agent model preflight validation and query-time error mapping (#176).

Covers:
- create_agent with a model the provider doesn't serve -> ValueError ("not available")
- create_agent with an unconfigured provider -> ValueError ("not configured")
- provider unreachable (list_models raises or returns []) -> save ALLOWED
- update_agent without a model change -> no validation performed
- update_agent with a model change -> validated
- OllamaProvider.chat() 404 -> actionable ValueError naming the model
- /api/agents/{id}/query surfaces the mapped error as HTTP 400
"""
from contextlib import asynccontextmanager

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app.providers.base import ChatMessage, MessageRole, ModelInfo
from app.providers.ollama import OllamaProvider
from app.services.agent_service import AgentService
from tests.factories import AgentFactory


def _model_info(model_id: str) -> ModelInfo:
    return ModelInfo(id=model_id, name=model_id, provider="ollama")


def _fake_provider(
    models: list[str] | None = None,
    configured: bool = True,
    list_error: Exception | None = None,
) -> MagicMock:
    """Build a mock LLM provider for preflight tests."""
    provider = MagicMock()
    provider.is_configured = configured
    if list_error is not None:
        provider.list_models = AsyncMock(side_effect=list_error)
    else:
        provider.list_models = AsyncMock(
            return_value=[_model_info(m) for m in (models or [])]
        )
    return provider


def _fake_registry(provider) -> MagicMock:
    registry = MagicMock()
    registry.get_provider.return_value = provider
    return registry


AVAILABLE_MODELS = ["gemma4:12b-mlx", "gemma4:26b-mlx", "gemma4:31b-mlx"]


class TestCreateAgentModelPreflight:
    """Preflight validation on agent creation."""

    @pytest.mark.asyncio
    async def test_create_with_unavailable_model_raises(
        self, db_session, enable_model_preflight
    ):
        provider = _fake_provider(models=AVAILABLE_MODELS)
        with patch(
            "app.services.agent_service.get_registry",
            return_value=_fake_registry(provider),
        ):
            service = AgentService(db_session)
            with pytest.raises(ValueError, match="not available"):
                await service.create_agent(
                    name="ACME Specialist",
                    system_prompt="You are helpful.",
                    model_provider="ollama",
                    model_name="gemma4:27b",
                )

    @pytest.mark.asyncio
    async def test_unavailable_model_error_lists_alternatives(
        self, db_session, enable_model_preflight
    ):
        provider = _fake_provider(models=AVAILABLE_MODELS)
        with patch(
            "app.services.agent_service.get_registry",
            return_value=_fake_registry(provider),
        ):
            service = AgentService(db_session)
            with pytest.raises(ValueError) as exc_info:
                await service.create_agent(
                    name="ACME Specialist",
                    system_prompt="You are helpful.",
                    model_provider="ollama",
                    model_name="gemma4:27b",
                )
        message = str(exc_info.value)
        assert "gemma4:27b" in message
        assert "gemma4:12b-mlx" in message

    @pytest.mark.asyncio
    async def test_create_with_unconfigured_provider_raises(
        self, db_session, enable_model_preflight
    ):
        registry = MagicMock()
        registry.get_provider.return_value = None  # provider not registered
        with patch(
            "app.services.agent_service.get_registry", return_value=registry
        ):
            service = AgentService(db_session)
            with pytest.raises(ValueError, match="not configured"):
                await service.create_agent(
                    name="ACME Specialist",
                    system_prompt="You are helpful.",
                    model_provider="openai",
                    model_name="gpt-4",
                )

    @pytest.mark.asyncio
    async def test_create_with_available_model_succeeds(
        self, db_session, enable_model_preflight
    ):
        provider = _fake_provider(models=AVAILABLE_MODELS)
        with patch(
            "app.services.agent_service.get_registry",
            return_value=_fake_registry(provider),
        ):
            service = AgentService(db_session)
            agent = await service.create_agent(
                name="ACME Specialist",
                system_prompt="You are helpful.",
                model_provider="ollama",
                model_name="gemma4:26b-mlx",
            )
        assert agent.model_name == "gemma4:26b-mlx"

    @pytest.mark.asyncio
    async def test_provider_unreachable_allows_save(
        self, db_session, enable_model_preflight
    ):
        """Listing models failing must NOT block the save (provider may be down)."""
        provider = _fake_provider(list_error=httpx.ConnectError("connection refused"))
        with patch(
            "app.services.agent_service.get_registry",
            return_value=_fake_registry(provider),
        ):
            service = AgentService(db_session)
            agent = await service.create_agent(
                name="ACME Specialist",
                system_prompt="You are helpful.",
                model_provider="ollama",
                model_name="gemma4:27b",
            )
        assert agent is not None
        assert agent.model_name == "gemma4:27b"

    @pytest.mark.asyncio
    async def test_empty_model_list_allows_save(
        self, db_session, enable_model_preflight
    ):
        """Ollama returns [] when unreachable — treated as unknown, save allowed."""
        provider = _fake_provider(models=[])
        with patch(
            "app.services.agent_service.get_registry",
            return_value=_fake_registry(provider),
        ):
            service = AgentService(db_session)
            agent = await service.create_agent(
                name="ACME Specialist",
                system_prompt="You are helpful.",
                model_provider="ollama",
                model_name="gemma4:27b",
            )
        assert agent is not None


class TestUpdateAgentModelPreflight:
    """Preflight validation on agent update — only when model fields change."""

    async def _persist_agent(self, db_session):
        agent = AgentFactory.create(
            agent_id="preflight-agent",
            model_provider="ollama",
            model_name="gemma4:26b-mlx",
        )
        db_session.add(agent)
        await db_session.commit()
        return agent

    @pytest.mark.asyncio
    async def test_update_without_model_change_skips_validation(self, db_session):
        """Editing unrelated fields must not trigger the preflight at all."""
        agent = await self._persist_agent(db_session)
        service = AgentService(db_session)

        with patch.object(
            AgentService, "_validate_model_available", new_callable=AsyncMock
        ) as spy:
            updated = await service.update_agent(agent.id, name="Renamed Agent")

        assert updated is not None
        assert updated.name == "Renamed Agent"
        spy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_with_same_model_values_skips_validation(self, db_session):
        """Re-sending the current provider/model is not a change."""
        agent = await self._persist_agent(db_session)
        service = AgentService(db_session)

        with patch.object(
            AgentService, "_validate_model_available", new_callable=AsyncMock
        ) as spy:
            updated = await service.update_agent(
                agent.id,
                model_provider="ollama",
                model_name="gemma4:26b-mlx",
            )

        assert updated is not None
        spy.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_to_unavailable_model_raises(
        self, db_session, enable_model_preflight
    ):
        agent = await self._persist_agent(db_session)
        provider = _fake_provider(models=AVAILABLE_MODELS)
        with patch(
            "app.services.agent_service.get_registry",
            return_value=_fake_registry(provider),
        ):
            service = AgentService(db_session)
            with pytest.raises(ValueError, match="not available"):
                await service.update_agent(agent.id, model_name="gemma4:27b")

    @pytest.mark.asyncio
    async def test_update_api_returns_400_on_unavailable_model(
        self, client, db_session, enable_model_preflight
    ):
        agent = await self._persist_agent(db_session)
        provider = _fake_provider(models=AVAILABLE_MODELS)
        with patch(
            "app.services.agent_service.get_registry",
            return_value=_fake_registry(provider),
        ):
            response = await client.put(
                f"/api/agents/{agent.id}",
                json={"model_name": "gemma4:27b"},
            )
        assert response.status_code == 400
        assert "not available" in response.json()["detail"]


class TestOllama404Mapping:
    """Query-time mapping of Ollama 404 to an actionable error."""

    def _provider_with_response(self, status_code: int) -> OllamaProvider:
        provider = OllamaProvider(base_url="http://ollama.test")
        request = httpx.Request("POST", "http://ollama.test/api/chat")
        response = httpx.Response(status_code, request=request)
        provider._client.post = AsyncMock(return_value=response)
        return provider

    @pytest.mark.asyncio
    async def test_chat_404_maps_to_value_error(self):
        provider = self._provider_with_response(404)
        with pytest.raises(ValueError, match="not found on Ollama"):
            await provider.chat(
                messages=[ChatMessage(role=MessageRole.USER, content="hi")],
                model="gemma4:27b",
            )
        await provider.close()

    @pytest.mark.asyncio
    async def test_chat_404_error_names_the_model(self):
        provider = self._provider_with_response(404)
        with pytest.raises(ValueError) as exc_info:
            await provider.chat(
                messages=[ChatMessage(role=MessageRole.USER, content="hi")],
                model="gemma4:27b",
            )
        assert "gemma4:27b" in str(exc_info.value)
        await provider.close()

    @pytest.mark.asyncio
    async def test_chat_non_404_http_error_reraised(self):
        """Other HTTP errors keep their original type (no over-mapping)."""
        provider = self._provider_with_response(500)
        with pytest.raises(httpx.HTTPStatusError):
            await provider.chat(
                messages=[ChatMessage(role=MessageRole.USER, content="hi")],
                model="gemma4:26b-mlx",
            )
        await provider.close()

    @pytest.mark.asyncio
    async def test_chat_stream_404_maps_to_value_error(self):
        """chat_stream() applies the same 404 mapping as chat()."""
        provider = OllamaProvider(base_url="http://ollama.test")
        request = httpx.Request("POST", "http://ollama.test/api/chat")
        response = httpx.Response(404, request=request)

        @asynccontextmanager
        async def _fake_stream(method, url, **kwargs):
            yield response

        provider._client.stream = _fake_stream
        with pytest.raises(ValueError, match="not found on Ollama"):
            async for _ in provider.chat_stream(
                messages=[ChatMessage(role=MessageRole.USER, content="hi")],
                model="gemma4:27b",
            ):
                pass
        await provider.close()

    @pytest.mark.asyncio
    async def test_query_endpoint_surfaces_model_not_found_as_400(
        self, client, db_session
    ):
        """The mapped ValueError reaches the API client as a 400, not a 500."""
        agent = AgentFactory.create(
            model_provider="ollama",
            model_name="gemma4:27b",
        )
        db_session.add(agent)
        await db_session.commit()

        mock_provider = MagicMock()
        mock_provider.chat = AsyncMock(
            side_effect=ValueError(
                "Model 'gemma4:27b' not found on Ollama — pull it "
                "(ollama pull gemma4:27b) or update the agent's model"
            )
        )
        with patch(
            "app.services.agent_query.ProviderService.get_provider",
            return_value=mock_provider,
        ):
            response = await client.post(
                f"/api/agents/{agent.id}/query",
                json={"query": "What is ACME's refund policy?"},
            )

        assert response.status_code == 400
        assert "not found on Ollama" in response.json()["detail"]
