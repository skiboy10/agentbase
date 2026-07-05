"""
Test factories for creating model instances with sensible defaults.
Provides consistent, reusable test data across all test files.
"""
from datetime import datetime, timezone
from typing import Optional, Any
from uuid import uuid4

from app.models.models import (
    Project, Source, IndexingLog,
    ProviderConfig, ModelAssignment, Prompt,
    Agent
)


class ProjectFactory:
    """Factory for creating Project instances."""

    @staticmethod
    def create(
        id: Optional[str] = None,
        name: str = "Test Project",
        description: Optional[str] = "Test project description",
        instructions: Optional[str] = None,
        **kwargs
    ) -> Project:
        return Project(
            id=id or str(uuid4()),
            name=name,
            description=description,
            instructions=instructions,
            created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
            updated_at=kwargs.get("updated_at", datetime.now(timezone.utc)),
        )

    @staticmethod
    def build_dict(**kwargs) -> dict:
        """Build a dict for API requests."""
        data = {
            "name": kwargs.get("name", "Test Project"),
            "description": kwargs.get("description", "Test project description"),
        }
        if "instructions" in kwargs:
            data["instructions"] = kwargs["instructions"]
        return data


class KnowledgeSourceFactory:
    """Factory for creating Source instances."""

    @staticmethod
    def create(
        id: Optional[str] = None,
        project_id: Optional[str] = None,
        name: str = "Test Knowledge Source",
        source_type: str = "url",
        source_path: str = "https://example.com/docs",
        description: Optional[str] = "Test source description",
        status: str = "pending",
        **kwargs
    ) -> Source:
        return Source(
            id=id or str(uuid4()),
            project_id=project_id,
            name=name,
            source_type=source_type,
            source_path=source_path,
            description=description,
            status=status,
            document_count=kwargs.get("document_count", 0),
            chunk_count=kwargs.get("chunk_count", 0),
            progress=kwargs.get("progress", 0),
            progress_total=kwargs.get("progress_total", 0),
            embedding_provider=kwargs.get("embedding_provider"),
            embedding_model=kwargs.get("embedding_model"),
            embedding_dimensions=kwargs.get("embedding_dimensions"),
            collection_name=kwargs.get("collection_name"),
            created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
            updated_at=kwargs.get("updated_at", datetime.now(timezone.utc)),
        )

    @staticmethod
    def build_dict(project_id: Optional[str] = None, **kwargs) -> dict:
        """Build a dict for API requests."""
        return {
            "project_id": project_id,
            "name": kwargs.get("name", "Test Knowledge Source"),
            "source_type": kwargs.get("source_type", "url"),
            "source_path": kwargs.get("source_path", "https://example.com/docs"),
            "description": kwargs.get("description", "Test source description"),
            "selected_urls": kwargs.get("selected_urls", [
                "https://example.com/docs/page1",
                "https://example.com/docs/page2",
            ]),
        }


class PromptFactory:
    """Factory for creating Prompt instances."""

    @staticmethod
    def create(
        id: Optional[str] = None,
        project_id: Optional[str] = None,
        name: str = "Test Prompt",
        system_prompt: str = "You are a helpful assistant.",
        task_type: str = "chat",
        is_default: bool = False,
        use_rag: bool = True,
        version: int = 1,
        **kwargs
    ) -> Prompt:
        return Prompt(
            id=id or str(uuid4()),
            project_id=project_id,
            name=name,
            description=kwargs.get("description"),
            system_prompt=system_prompt,
            task_type=task_type,
            is_default=is_default,
            use_rag=use_rag,
            version=version,
            rag_context_template=kwargs.get("rag_context_template"),
            created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
            updated_at=kwargs.get("updated_at", datetime.now(timezone.utc)),
        )

    @staticmethod
    def build_dict(project_id: Optional[str] = None, **kwargs) -> dict:
        """Build a dict for API requests."""
        return {
            "project_id": project_id,
            "name": kwargs.get("name", "Test Prompt"),
            "system_prompt": kwargs.get("system_prompt", "You are a helpful assistant."),
            "task_type": kwargs.get("task_type", "chat"),
            "is_default": kwargs.get("is_default", False),
            "use_rag": kwargs.get("use_rag", True),
            "rag_context_template": kwargs.get("rag_context_template"),
        }


class ProviderConfigFactory:
    """Factory for creating ProviderConfig instances."""

    @staticmethod
    def create(
        id: Optional[str] = None,
        provider_name: str = "ollama",
        api_key_encrypted: Optional[str] = None,
        base_url: Optional[str] = "http://localhost:11434",
        **kwargs
    ) -> ProviderConfig:
        return ProviderConfig(
            id=id or str(uuid4()),
            provider_name=provider_name,
            api_key_encrypted=api_key_encrypted,
            base_url=base_url,
            is_active=kwargs.get("is_active", True),
            created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
            updated_at=kwargs.get("updated_at", datetime.now(timezone.utc)),
        )


class AgentFactory:
    """Factory for creating Agent instances."""

    @staticmethod
    def create(
        id: Optional[str] = None,
        agent_id: Optional[str] = None,
        name: str = "Test Agent",
        system_prompt: str = "You are a helpful test assistant.",
        model_provider: str = "openai",
        model_name: str = "gpt-4",
        description: Optional[str] = "Test agent description",
        temperature: float = 0.7,
        use_rag: bool = False,
        rag_top_k: int = 5,
        **kwargs
    ) -> Agent:
        return Agent(
            id=id or str(uuid4()),
            agent_id=agent_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            model_provider=model_provider,
            model_name=model_name,
            temperature=temperature,
            use_rag=use_rag,
            rag_top_k=rag_top_k,
            skills=kwargs.get("skills", []),
            is_public=kwargs.get("is_public", False),
            created_at=kwargs.get("created_at", datetime.now(timezone.utc)),
            updated_at=kwargs.get("updated_at", datetime.now(timezone.utc)),
        )

    @staticmethod
    def build_dict(**kwargs) -> dict:
        """Build a dict for API requests."""
        return {
            "name": kwargs.get("name", "Test Agent"),
            "system_prompt": kwargs.get("system_prompt", "You are a helpful test assistant."),
            "model_provider": kwargs.get("model_provider", "openai"),
            "model_name": kwargs.get("model_name", "gpt-4"),
            "description": kwargs.get("description", "Test agent description"),
            "temperature": kwargs.get("temperature", 0.7),
            "use_rag": kwargs.get("use_rag", False),
            "rag_top_k": kwargs.get("rag_top_k", 5),
            "is_public": kwargs.get("is_public", False),
        }


# Convenience functions for quick test data creation
def create_project_with_sources(db_session, num_sources: int = 2) -> tuple[Project, list[Source]]:
    """Create a project with knowledge sources."""
    project = ProjectFactory.create()
    sources = [
        KnowledgeSourceFactory.create(
            project_id=project.id,
            name=f"Source {i}",
            source_path=f"https://example.com/docs{i}"
        )
        for i in range(num_sources)
    ]
    return project, sources


