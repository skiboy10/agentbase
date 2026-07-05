"""
Pytest configuration and fixtures for Agentbase tests.
"""
import os
import pytest
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Set test environment before importing app
os.environ["TESTING"] = "true"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"

from app.main import app
from app.core.database import Base, get_db
from app.services.agent_service import AgentService
from tests.factories import (
    ProjectFactory, KnowledgeSourceFactory, PromptFactory,
    ProviderConfigFactory, AgentFactory
)


@pytest.fixture(autouse=True)
def _skip_model_preflight(request, monkeypatch):
    """
    Disable agent model preflight validation by default.

    The preflight (#176) consults the live provider registry — a network
    dependency tests must not have. Tests that exercise the validation itself
    opt back in by requesting the `enable_model_preflight` fixture.
    """
    if "enable_model_preflight" in request.fixturenames:
        return

    async def _noop(self, provider_name: str, model_name: str) -> None:
        return None

    monkeypatch.setattr(AgentService, "_validate_model_available", _noop)


@pytest.fixture
def enable_model_preflight():
    """Marker fixture: keep the real model preflight active for this test."""
    return None


# Create test database engine
test_engine = create_async_engine(
    "sqlite+aiosqlite:///./test.db",
    echo=False,
)

test_session_maker = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@pytest.fixture(scope="function")
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    # Create tables
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with test_session_maker() as session:
        yield session

    # Drop tables after test
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client with overridden database dependency."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=True) as ac:
        yield ac

    app.dependency_overrides.clear()


# =============
# Data Fixtures using Factories
# =============

@pytest.fixture
def sample_project_data():
    """Sample project data for testing."""
    return ProjectFactory.build_dict()


@pytest.fixture
def sample_source_data():
    """Sample knowledge source data for testing."""
    return KnowledgeSourceFactory.build_dict()


@pytest.fixture
def sample_prompt_data():
    """Sample prompt data for testing."""
    return PromptFactory.build_dict()


# =============
# Model Instance Fixtures
# =============

@pytest.fixture
async def project(db_session: AsyncSession):
    """Create and persist a project."""
    project = ProjectFactory.create()
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


@pytest.fixture
async def knowledge_source(db_session: AsyncSession, project):
    """Create and persist a knowledge source."""
    source = KnowledgeSourceFactory.create(project_id=project.id)
    db_session.add(source)
    await db_session.commit()
    await db_session.refresh(source)
    return source


@pytest.fixture
async def prompt(db_session: AsyncSession, project):
    """Create and persist a prompt."""
    prompt = PromptFactory.create(project_id=project.id)
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    return prompt


# =============
# Mock Fixtures
# =============

@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider for testing without actual API calls."""
    provider = MagicMock()
    provider.chat = AsyncMock(return_value={
        "content": "This is a mock response from the LLM.",
        "model": "mock-model",
        "input_tokens": 10,
        "output_tokens": 20,
    })
    provider.chat_stream = AsyncMock()
    provider.list_models = AsyncMock(return_value=["model-1", "model-2"])
    provider.health_check = AsyncMock(return_value=True)
    return provider


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client for vector operations."""
    client = MagicMock()
    client.search = AsyncMock(return_value=[
        MagicMock(
            payload={"content": "Relevant context", "source": "https://example.com"},
            score=0.95
        )
    ])
    client.upsert = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service."""
    service = MagicMock()
    service.embed = AsyncMock(return_value=[0.1] * 1024)
    service.embed_batch = AsyncMock(return_value=[[0.1] * 1024 for _ in range(10)])
    return service
