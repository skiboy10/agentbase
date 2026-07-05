"""
Tests for Knowledge Base API endpoints.

Tests cover:
- Knowledge source CRUD operations
- Source update (rename, description)
- URL management (add/remove)
- Refresh functionality
- Embedding config storage
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AgentSource
from tests.factories import AgentFactory, KnowledgeSourceFactory


class TestKnowledgeSourceCRUD:
    """Tests for basic CRUD operations on knowledge sources."""

    @pytest.mark.asyncio
    async def test_create_project(self, client: AsyncClient, sample_project_data):
        """Test creating a project (required for knowledge sources)."""
        response = await client.post("/api/projects", json=sample_project_data)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_project_data["name"]
        assert data["description"] == sample_project_data["description"]
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_knowledge_source(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test creating a knowledge source."""
        # First create a project
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        # Create knowledge source with project_id
        source_data = {**sample_source_data, "project_id": project["id"]}
        response = await client.post("/api/sources", json=source_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_source_data["name"]
        assert data["description"] == sample_source_data["description"]
        assert data["source_type"] == "url"
        assert data["status"] == "pending"
        assert data["selected_urls"] == sample_source_data["selected_urls"]
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_knowledge_sources(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test listing knowledge sources."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        await client.post("/api/sources", json=source_data)

        # List sources
        response = await client.get(f"/api/sources?project_id={project['id']}")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["name"] == sample_source_data["name"]

    @pytest.mark.asyncio
    async def test_get_knowledge_source(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test getting a specific knowledge source."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Get source
        response = await client.get(f"/api/sources/{source['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == source["id"]
        assert data["name"] == sample_source_data["name"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_source(self, client: AsyncClient):
        """Test getting a source that doesn't exist."""
        response = await client.get("/api/sources/nonexistent-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_knowledge_source(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test deleting a knowledge source."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Delete source
        response = await client.delete(f"/api/sources/{source['id']}")
        assert response.status_code == 204

        # Verify deleted
        get_response = await client.get(f"/api/sources/{source['id']}")
        assert get_response.status_code == 404


class TestBoundAgents:
    """Tests for agent binding info in source listings.

    Regression coverage for #170: list_knowledge_sources 500'd when building
    bound_agents after Agent.project_id was dropped (#123), because no test
    exercised the listing path with an AgentSource binding present.
    """

    @pytest.mark.asyncio
    async def test_list_sources_includes_bound_agents(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Listing sources returns bound_agents for sources with agent bindings."""
        agent = AgentFactory.create(name="Bound Agent")
        bound_source = KnowledgeSourceFactory.create(name="Bound Source")
        unbound_source = KnowledgeSourceFactory.create(
            name="Unbound Source",
            source_path="https://example.com/other-docs",
        )
        db_session.add_all([
            agent, bound_source, unbound_source,
            AgentSource(agent_id=agent.id, source_id=bound_source.id),
        ])
        await db_session.commit()

        response = await client.get("/api/sources")
        assert response.status_code == 200
        data = response.json()
        sources_by_id = {s["id"]: s for s in data}

        assert bound_source.id in sources_by_id
        assert unbound_source.id in sources_by_id

        bound = sources_by_id[bound_source.id]
        assert bound["bound_agents"] == [{"id": agent.id, "name": "Bound Agent"}]

        unbound = sources_by_id[unbound_source.id]
        assert unbound["bound_agents"] == []

    @pytest.mark.asyncio
    async def test_list_sources_multiple_bound_agents(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """A source bound to multiple agents lists all of them."""
        agents = [AgentFactory.create(name=f"Agent {i}") for i in range(2)]
        source = KnowledgeSourceFactory.create(name="Shared Source")
        db_session.add_all([
            *agents,
            source,
            *(AgentSource(agent_id=a.id, source_id=source.id) for a in agents),
        ])
        await db_session.commit()

        response = await client.get("/api/sources")
        assert response.status_code == 200
        sources_by_id = {s["id"]: s for s in response.json()}

        assert source.id in sources_by_id
        bound_agents = sources_by_id[source.id]["bound_agents"]
        expected = sorted(
            ({"id": a.id, "name": a.name} for a in agents),
            key=lambda a: a["name"],
        )
        assert sorted(bound_agents, key=lambda a: a["name"]) == expected


class TestKnowledgeSourceUpdate:
    """Tests for updating knowledge source metadata."""

    @pytest.mark.asyncio
    async def test_update_source_name(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test updating a source's name."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Update name
        update_data = {"name": "Updated Documentation Name"}
        response = await client.put(f"/api/sources/{source['id']}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Documentation Name"
        assert data["description"] == sample_source_data["description"]  # Unchanged

    @pytest.mark.asyncio
    async def test_update_source_description(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test updating a source's description."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Update description
        update_data = {"description": "New detailed description"}
        response = await client.put(f"/api/sources/{source['id']}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "New detailed description"
        assert data["name"] == sample_source_data["name"]  # Unchanged

    @pytest.mark.asyncio
    async def test_update_source_both_fields(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test updating both name and description."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Update both
        update_data = {
            "name": "Renamed Source",
            "description": "Updated description"
        }
        response = await client.put(f"/api/sources/{source['id']}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Renamed Source"
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_nonexistent_source(self, client: AsyncClient):
        """Test updating a source that doesn't exist."""
        update_data = {"name": "New Name"}
        response = await client.put("/api/sources/nonexistent-id", json=update_data)
        assert response.status_code == 404


class TestURLManagement:
    """Tests for URL management within sources."""

    @pytest.mark.asyncio
    async def test_add_urls_to_source(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test adding new URLs to an existing source."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        original_count = len(source["selected_urls"])

        # Add new URLs
        new_urls = [
            "https://example.com/docs/page4",
            "https://example.com/docs/page5",
        ]
        response = await client.post(
            f"/api/sources/{source['id']}/urls",
            json={"urls": new_urls}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["selected_urls"]) == original_count + 2
        assert "https://example.com/docs/page4" in data["selected_urls"]
        assert "https://example.com/docs/page5" in data["selected_urls"]

    @pytest.mark.asyncio
    async def test_add_duplicate_urls(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test that adding duplicate URLs doesn't create duplicates."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        original_count = len(source["selected_urls"])

        # Try to add existing URL
        duplicate_urls = ["https://example.com/docs/page1"]  # Already exists
        response = await client.post(
            f"/api/sources/{source['id']}/urls",
            json={"urls": duplicate_urls}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["selected_urls"]) == original_count  # No change

    @pytest.mark.asyncio
    async def test_remove_urls_from_source(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test removing URLs from a source."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        original_count = len(source["selected_urls"])

        # Remove one URL
        urls_to_remove = ["https://example.com/docs/page1"]
        response = await client.request(
            "DELETE",
            f"/api/sources/{source['id']}/urls",
            json={"urls": urls_to_remove}
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["selected_urls"]) == original_count - 1
        assert "https://example.com/docs/page1" not in data["selected_urls"]

    @pytest.mark.asyncio
    async def test_add_urls_to_non_url_source(self, client: AsyncClient, sample_project_data):
        """Test that adding URLs to a non-URL source fails."""
        # Create project
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        # Create directory source
        source_data = {
            "name": "Directory Source",
            "source_type": "directory",
            "source_path": "/path/to/docs",
            "project_id": project["id"]
        }
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Try to add URLs
        response = await client.post(
            f"/api/sources/{source['id']}/urls",
            json={"urls": ["https://example.com"]}
        )

        assert response.status_code == 400


class TestRefreshSource:
    """Tests for source refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_full_mode(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test full refresh mode."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Request full refresh
        response = await client.post(
            f"/api/sources/{source['id']}/refresh",
            json={"mode": "full"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "full"
        assert data["status"] == "indexing"

    @pytest.mark.asyncio
    async def test_refresh_selective_mode(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test selective refresh mode with specific URLs."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Request selective refresh
        urls_to_refresh = ["https://example.com/docs/page1"]
        response = await client.post(
            f"/api/sources/{source['id']}/refresh",
            json={"mode": "selective", "urls": urls_to_refresh}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["mode"] == "selective"
        assert data["url_count"] == 1

    @pytest.mark.asyncio
    async def test_refresh_selective_without_urls(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test that selective refresh without URLs fails."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Request selective refresh without URLs
        response = await client.post(
            f"/api/sources/{source['id']}/refresh",
            json={"mode": "selective"}  # No URLs
        )

        assert response.status_code == 400


class TestEmbeddingConfig:
    """Tests for embedding configuration storage."""

    @pytest.mark.asyncio
    async def test_source_has_embedding_fields(self, client: AsyncClient, sample_project_data, sample_source_data):
        """Test that source response includes embedding fields."""
        # Create project and source
        project_response = await client.post("/api/projects", json=sample_project_data)
        project = project_response.json()

        source_data = {**sample_source_data, "project_id": project["id"]}
        create_response = await client.post("/api/sources", json=source_data)
        source = create_response.json()

        # Check embedding fields exist (null initially)
        assert "embedding_provider" in source
        assert "embedding_model" in source
        assert "embedding_dimensions" in source

        # They should be null before indexing
        assert source["embedding_provider"] is None
        assert source["embedding_model"] is None
        assert source["embedding_dimensions"] is None


class TestHealthCheck:
    """Tests for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        """Test the health check endpoint."""
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
