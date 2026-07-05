"""
Tests for Agent Service - focusing on agent_id auto-generation.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_service import AgentService, generate_agent_id
from app.models import Agent
from tests.factories import AgentFactory


class TestGenerateAgentId:
    """Unit tests for the generate_agent_id function."""

    def test_basic_conversion(self):
        """Test basic name to agent_id conversion."""
        assert generate_agent_id("Test Agent") == "test-agent"

    def test_multiple_spaces(self):
        """Test handling of multiple spaces."""
        assert generate_agent_id("Test   Agent") == "test-agent"

    def test_underscores_converted(self):
        """Test that underscores are converted to hyphens."""
        assert generate_agent_id("test_agent_name") == "test-agent-name"

    def test_special_characters_removed(self):
        """Test that special characters are removed."""
        assert generate_agent_id("Test Agent (v2)") == "test-agent-v2"
        assert generate_agent_id("My Agent!@#$%") == "my-agent"

    def test_mixed_case(self):
        """Test that mixed case is converted to lowercase."""
        assert generate_agent_id("UPPERCASE Agent") == "uppercase-agent"
        assert generate_agent_id("CamelCaseAgent") == "camelcaseagent"

    def test_leading_trailing_hyphens_stripped(self):
        """Test that leading/trailing hyphens are stripped."""
        assert generate_agent_id("--test-agent--") == "test-agent"
        assert generate_agent_id("   Test Agent   ") == "test-agent"

    def test_real_world_examples(self):
        """Test with real-world agent names."""
        assert generate_agent_id("Customer Support Analyzer") == "customer-support-analyzer"
        assert generate_agent_id("ACME Data Importer") == "acme-data-importer"
        assert generate_agent_id("Calculator Agent") == "calculator-agent"
        assert generate_agent_id("Test Agent (v2)") == "test-agent-v2"

    def test_numbers_preserved(self):
        """Test that numbers are preserved in the slug."""
        assert generate_agent_id("Agent 123") == "agent-123"
        assert generate_agent_id("GPT-4 Assistant") == "gpt-4-assistant"

    def test_unicode_characters_removed(self):
        """Test that unicode/emoji characters are removed."""
        assert generate_agent_id("Test Agent \ud83d\ude00") == "test-agent"
        assert generate_agent_id("Caf\u00e9 Bot") == "caf-bot"


class TestAgentServiceUniqueAgentId:
    """Integration tests for unique agent_id generation."""

    @pytest.mark.asyncio
    async def test_unique_agent_id_no_conflict(self, db_session: AsyncSession):
        """Test that a unique agent_id is generated when no conflict exists."""
        service = AgentService(db_session)

        agent_id = await service._generate_unique_agent_id("New Test Agent")

        assert agent_id == "new-test-agent"

    @pytest.mark.asyncio
    async def test_unique_agent_id_with_conflict(self, db_session: AsyncSession):
        """Test that suffix is added when agent_id already exists."""
        # Create an agent with the base slug
        existing = AgentFactory.create(agent_id="test-agent", name="Test Agent")
        db_session.add(existing)
        await db_session.commit()

        service = AgentService(db_session)

        # Should get -2 suffix since "test-agent" is taken
        agent_id = await service._generate_unique_agent_id("Test Agent")

        assert agent_id == "test-agent-2"

    @pytest.mark.asyncio
    async def test_unique_agent_id_multiple_conflicts(self, db_session: AsyncSession):
        """Test incrementing suffix with multiple conflicts."""
        # Create agents with base slug and -2 suffix
        db_session.add(AgentFactory.create(agent_id="test-agent", name="Test Agent"))
        db_session.add(AgentFactory.create(agent_id="test-agent-2", name="Test Agent 2"))
        await db_session.commit()

        service = AgentService(db_session)

        # Should get -3 suffix
        agent_id = await service._generate_unique_agent_id("Test Agent")

        assert agent_id == "test-agent-3"


class TestAgentServiceCreateAgent:
    """Integration tests for agent creation with auto-generated agent_id."""

    @pytest.mark.asyncio
    async def test_create_agent_generates_agent_id(self, db_session: AsyncSession):
        """Test that creating an agent auto-generates agent_id."""
        service = AgentService(db_session)

        agent = await service.create_agent(
            name="My New Agent",
            system_prompt="You are helpful.",
            model_provider="openai",
            model_name="gpt-4",
        )

        assert agent.agent_id == "my-new-agent"

    @pytest.mark.asyncio
    async def test_create_agent_handles_duplicate_names(self, db_session: AsyncSession):
        """Test that duplicate agent names get unique agent_ids."""
        service = AgentService(db_session)

        # Create first agent
        agent1 = await service.create_agent(
            name="Test Agent",
            system_prompt="First agent",
            model_provider="openai",
            model_name="gpt-4",
        )

        # Create second agent with same name
        agent2 = await service.create_agent(
            name="Test Agent",
            system_prompt="Second agent",
            model_provider="openai",
            model_name="gpt-4",
        )

        assert agent1.agent_id == "test-agent"
        assert agent2.agent_id == "test-agent-2"

    @pytest.mark.asyncio
    async def test_create_agent_generates_agent_id_from_name(self, db_session: AsyncSession):
        """Test that agent_id is auto-generated from the agent name."""
        service = AgentService(db_session)

        agent = await service.create_agent(
            name="Helper Agent",
            system_prompt="I help everyone.",
            model_provider="anthropic",
            model_name="claude-3",
        )

        assert agent.agent_id == "helper-agent"


class TestAgentApiEndpoints:
    """Integration tests for agent API endpoints."""

    @pytest.mark.asyncio
    async def test_create_agent_api_returns_agent_id(self, client, db_session):
        """Test that the API returns agent_id in the response."""
        response = await client.post("/api/agents", json={
            "name": "API Test Agent",
            "system_prompt": "Test prompt",
            "model_provider": "openai",
            "model_name": "gpt-4",
        })

        assert response.status_code == 201
        data = response.json()
        assert data["agent_id"] == "api-test-agent"

    @pytest.mark.asyncio
    async def test_list_agents_includes_agent_id(self, client, db_session):
        """Test that listing agents includes agent_id."""
        agent = AgentFactory.create(
            agent_id="listed-agent",
            name="Listed Agent"
        )
        db_session.add(agent)
        await db_session.commit()

        response = await client.get("/api/agents")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["agent_id"] == "listed-agent"

    @pytest.mark.asyncio
    async def test_get_agent_includes_agent_id(self, client, db_session):
        """Test that getting a single agent includes agent_id."""
        agent = AgentFactory.create(
            agent_id="single-agent",
            name="Single Agent"
        )
        db_session.add(agent)
        await db_session.commit()

        response = await client.get(f"/api/agents/{agent.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == "single-agent"
