"""
Tests for the Prompts API endpoints.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import PromptFactory, ProjectFactory


class TestPromptsAPI:
    """Test suite for /api/prompts/prompts endpoints."""

    async def test_create_prompt(self, client: AsyncClient, project):
        """Test creating a new prompt."""
        prompt_data = {
            "project_id": project.id,
            "name": "Test Prompt",
            "system_prompt": "You are a helpful assistant.",
            "task_type": "chat",
        }
        response = await client.post("/api/prompts/prompts", json=prompt_data)

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Prompt"
        assert data["system_prompt"] == "You are a helpful assistant."
        assert data["task_type"] == "chat"
        assert data["version"] == 1
        assert "id" in data

    async def test_create_global_prompt(self, client: AsyncClient):
        """Test creating a global prompt (no project_id)."""
        prompt_data = {
            "name": "Global Prompt",
            "system_prompt": "You are a helpful assistant.",
            "task_type": "chat",
        }
        response = await client.post("/api/prompts/prompts", json=prompt_data)

        assert response.status_code == 201
        data = response.json()
        assert data["project_id"] is None

    async def test_create_prompt_with_rag_template(self, client: AsyncClient, project):
        """Test creating a prompt with RAG template."""
        prompt_data = {
            "project_id": project.id,
            "name": "RAG Prompt",
            "system_prompt": "You are a documentation assistant.",
            "task_type": "chat",
            "rag_context_template": "Context: {context}\n\nQuestion: {question}",
        }
        response = await client.post("/api/prompts/prompts", json=prompt_data)

        assert response.status_code == 201
        data = response.json()
        assert data["rag_context_template"] == "Context: {context}\n\nQuestion: {question}"

    async def test_list_prompts(self, client: AsyncClient, db_session: AsyncSession, project):
        """Test listing all prompts."""
        # Create some prompts
        for i in range(3):
            prompt = PromptFactory.create(
                project_id=project.id,
                name=f"Prompt {i}"
            )
            db_session.add(prompt)
        await db_session.commit()

        # Query with project_id to get project-scoped prompts
        response = await client.get(f"/api/prompts/prompts?project_id={project.id}&include_global=true")

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

    async def test_list_prompts_by_project(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test filtering prompts by project."""
        # Create two projects with prompts
        project1 = ProjectFactory.create(name="Project 1")
        project2 = ProjectFactory.create(name="Project 2")
        db_session.add_all([project1, project2])
        await db_session.commit()

        for i in range(2):
            db_session.add(PromptFactory.create(project_id=project1.id, name=f"P1 Prompt {i}"))
            db_session.add(PromptFactory.create(project_id=project2.id, name=f"P2 Prompt {i}"))
        await db_session.commit()

        response = await client.get(f"/api/prompts/prompts?project_id={project1.id}&include_global=true")

        assert response.status_code == 200
        data = response.json()
        # Should get project1 prompts plus any global prompts
        for prompt in data:
            assert prompt["project_id"] in [project1.id, None]

    async def test_get_prompt(self, client: AsyncClient, prompt):
        """Test getting a specific prompt."""
        response = await client.get(f"/api/prompts/prompts/{prompt.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == prompt.id
        assert data["name"] == prompt.name

    async def test_get_prompt_not_found(self, client: AsyncClient):
        """Test getting a non-existent prompt."""
        response = await client.get("/api/prompts/prompts/nonexistent-id")

        assert response.status_code == 404

    async def test_update_prompt(self, client: AsyncClient, prompt):
        """Test updating a prompt."""
        update_data = {
            "name": "Updated Prompt",
            "system_prompt": "Updated content.",
        }
        response = await client.put(f"/api/prompts/prompts/{prompt.id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Prompt"
        assert data["system_prompt"] == "Updated content."

    async def test_delete_prompt(self, client: AsyncClient, prompt):
        """Test deleting a prompt."""
        response = await client.delete(f"/api/prompts/prompts/{prompt.id}")

        assert response.status_code == 200

        # Verify it's deleted
        get_response = await client.get(f"/api/prompts/prompts/{prompt.id}")
        assert get_response.status_code == 404

    async def test_get_default_prompt(self, client: AsyncClient, db_session: AsyncSession):
        """Test getting the default prompt for a task type."""
        # Create a default prompt
        default_prompt = PromptFactory.create(
            name="Default Chat",
            task_type="chat",
            is_default=True
        )
        db_session.add(default_prompt)
        await db_session.commit()

        response = await client.get("/api/prompts/prompts/default/chat")

        assert response.status_code == 200
        data = response.json()
        assert data["is_default"] is True
        assert data["task_type"] == "chat"


class TestPromptVersioning:
    """Test prompt versioning functionality."""

    async def test_duplicate_prompt(self, client: AsyncClient, prompt):
        """Test duplicating a prompt creates a new version."""
        response = await client.post(
            f"/api/prompts/prompts/{prompt.id}/duplicate",
            json={"new_name": f"{prompt.name} (copy)"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["id"] != prompt.id
        assert data["name"] == f"{prompt.name} (copy)"
        assert data["system_prompt"] == prompt.system_prompt

    async def test_prompt_version_increments(
        self, client: AsyncClient, db_session: AsyncSession, project
    ):
        """Test that prompt version increments correctly."""
        prompt_data = {
            "project_id": project.id,
            "name": "Versioned Prompt",
            "system_prompt": "Version 1 content.",
            "task_type": "chat",
        }

        # Create first version
        response1 = await client.post("/api/prompts/prompts", json=prompt_data)
        assert response1.status_code == 201
        assert response1.json()["version"] == 1
