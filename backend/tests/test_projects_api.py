"""
Tests for the Projects API endpoints.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import ProjectFactory


class TestProjectsAPI:
    """Test suite for /api/projects endpoints."""

    async def test_create_project(self, client: AsyncClient, sample_project_data):
        """Test creating a new project."""
        response = await client.post("/api/projects", json=sample_project_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == sample_project_data["name"]
        assert data["description"] == sample_project_data["description"]
        assert "id" in data
        assert "created_at" in data

    async def test_create_project_without_description(self, client: AsyncClient):
        """Test creating a project without a description."""
        project_data = {"name": "Minimal Project"}
        response = await client.post("/api/projects", json=project_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Project"
        assert data["description"] is None

    async def test_create_project_empty_name(self, client: AsyncClient):
        """Test creating a project with empty name (currently allowed)."""
        response = await client.post("/api/projects", json={"name": ""})

        # API currently accepts empty names
        assert response.status_code == 201

    async def test_list_projects(self, client: AsyncClient, db_session: AsyncSession):
        """Test listing all projects."""
        # Create some projects
        for i in range(3):
            project = ProjectFactory.create(name=f"Project {i}")
            db_session.add(project)
        await db_session.commit()

        response = await client.get("/api/projects")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

    async def test_list_projects_empty(self, client: AsyncClient):
        """Test listing projects when none exist."""
        response = await client.get("/api/projects")

        assert response.status_code == 200
        assert response.json() == []

    async def test_get_project(self, client: AsyncClient, project):
        """Test getting a specific project."""
        response = await client.get(f"/api/projects/{project.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == project.id
        assert data["name"] == project.name

    async def test_get_project_not_found(self, client: AsyncClient):
        """Test getting a non-existent project."""
        response = await client.get("/api/projects/nonexistent-id")

        assert response.status_code == 404

    async def test_update_project(self, client: AsyncClient, project):
        """Test updating a project."""
        update_data = {
            "name": "Updated Name",
            "description": "Updated description"
        }
        response = await client.put(f"/api/projects/{project.id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["description"] == "Updated description"

    async def test_update_project_partial(self, client: AsyncClient, project):
        """Test partially updating a project (only name)."""
        update_data = {"name": "New Name Only"}
        response = await client.put(f"/api/projects/{project.id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name Only"

    async def test_update_project_not_found(self, client: AsyncClient):
        """Test updating a non-existent project."""
        response = await client.put(
            "/api/projects/nonexistent-id",
            json={"name": "Test"}
        )

        assert response.status_code == 404

    async def test_delete_project(self, client: AsyncClient, project):
        """Test deleting a project."""
        response = await client.delete(f"/api/projects/{project.id}")

        assert response.status_code == 204

        # Verify it's deleted
        get_response = await client.get(f"/api/projects/{project.id}")
        assert get_response.status_code == 404

    async def test_delete_project_not_found(self, client: AsyncClient):
        """Test deleting a non-existent project."""
        response = await client.delete("/api/projects/nonexistent-id")

        assert response.status_code == 404


class TestProjectInstructions:
    """Test suite for project instructions feature."""

    async def test_create_project_returns_null_instructions(self, client: AsyncClient):
        """Test that new projects have null instructions by default."""
        project_data = {"name": "Project Without Instructions"}
        response = await client.post("/api/projects", json=project_data)

        assert response.status_code == 201
        data = response.json()
        assert data["instructions"] is None

    async def test_update_project_with_instructions(self, client: AsyncClient, project):
        """Test updating a project with instructions."""
        update_data = {
            "instructions": "Always use formal language. Never mention competitors."
        }
        response = await client.put(f"/api/projects/{project.id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["instructions"] == "Always use formal language. Never mention competitors."

    async def test_get_project_includes_instructions(self, client: AsyncClient, db_session: AsyncSession):
        """Test that getting a project includes instructions."""
        project = ProjectFactory.create(
            name="Project With Instructions",
            instructions="These are test instructions for the project."
        )
        db_session.add(project)
        await db_session.commit()

        response = await client.get(f"/api/projects/{project.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["instructions"] == "These are test instructions for the project."

    async def test_list_projects_includes_instructions(self, client: AsyncClient, db_session: AsyncSession):
        """Test that listing projects includes instructions."""
        project = ProjectFactory.create(
            name="Project With Instructions",
            instructions="List test instructions"
        )
        db_session.add(project)
        await db_session.commit()

        response = await client.get("/api/projects")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["instructions"] == "List test instructions"

    async def test_update_project_clear_instructions(self, client: AsyncClient, db_session: AsyncSession):
        """Test clearing project instructions by setting to empty string."""
        project = ProjectFactory.create(
            name="Project",
            instructions="Original instructions"
        )
        db_session.add(project)
        await db_session.commit()

        update_data = {"instructions": ""}
        response = await client.put(f"/api/projects/{project.id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["instructions"] == ""

    async def test_update_project_multiline_instructions(self, client: AsyncClient, project):
        """Test updating project with multiline instructions."""
        multiline_instructions = """## Client Guidelines

1. Always greet the user warmly
2. Use their name when possible
3. Follow brand voice guidelines

## Terminology
- Use "member" not "customer"
- Use "solution" not "product"
"""
        update_data = {"instructions": multiline_instructions}
        response = await client.put(f"/api/projects/{project.id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["instructions"] == multiline_instructions
        assert "Client Guidelines" in data["instructions"]
        assert "Terminology" in data["instructions"]


class TestProjectsWithRelations:
    """Test projects with related entities."""

    async def test_project_with_knowledge_sources(
        self, client: AsyncClient, project, knowledge_source
    ):
        """Test that project can be retrieved with knowledge sources."""
        response = await client.get(f"/api/projects/{project.id}")

        assert response.status_code == 200

    async def test_project_with_prompts(
        self, client: AsyncClient, project, prompt
    ):
        """Test that project can be retrieved with prompts."""
        response = await client.get(f"/api/projects/{project.id}")

        assert response.status_code == 200
