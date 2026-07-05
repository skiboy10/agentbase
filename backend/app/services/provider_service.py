"""
Provider Service - Manages LLM provider routing and configuration.

This service provides:
- Provider health checking and status
- Model assignment management
- Provider configuration
"""
from typing import Optional
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.config import get_settings
from app.core.encryption import encrypt_credential
from app.models import ProviderConfig, ModelAssignment
from app.providers.registry import get_registry
from app.providers.base import LLMProvider

settings = get_settings()
logger = structlog.get_logger()


@dataclass
class ProviderStatus:
    """Status information for an LLM provider."""
    name: str
    is_configured: bool
    is_healthy: bool
    models: list[str]
    error: Optional[str] = None


@dataclass
class ModelAssignmentInfo:
    """Model assignment information."""
    task_type: str
    provider: str
    model: str
    project_id: Optional[str] = None


class ProviderService:
    """
    Service for LLM provider management.

    Handles:
    - Provider health checks
    - Model availability
    - Task-to-model routing
    - Provider configuration
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.registry = get_registry()

    async def get_provider_status(self, provider_name: str) -> ProviderStatus:
        """Get status for a specific provider."""
        provider = self.registry.get_provider(provider_name)

        if not provider:
            return ProviderStatus(
                name=provider_name,
                is_configured=False,
                is_healthy=False,
                models=[],
                error="Provider not found"
            )

        # Check health
        is_healthy = False
        error = None
        models = []

        if provider.is_configured:
            try:
                is_healthy = await provider.health_check()
                if is_healthy:
                    model_list = await provider.list_models()
                    models = [m.id for m in model_list]
            except Exception as e:
                error = str(e)
                logger.warning(
                    "Provider health check failed",
                    provider=provider_name,
                    error=error
                )

        return ProviderStatus(
            name=provider_name,
            is_configured=provider.is_configured,
            is_healthy=is_healthy,
            models=models,
            error=error
        )

    async def get_all_provider_statuses(self) -> list[ProviderStatus]:
        """Get status for all registered providers."""
        statuses = []
        for name in self.registry.list_providers():
            status = await self.get_provider_status(name)
            statuses.append(status)
        return statuses

    async def get_available_models(self) -> dict[str, list[str]]:
        """Get all available models grouped by provider."""
        result = {}
        for name in self.registry.list_providers():
            provider = self.registry.get_provider(name)
            if provider and provider.is_configured:
                try:
                    models = await provider.list_models()
                    result[name] = [m.id for m in models]
                except Exception as e:
                    logger.warning(f"Failed to list models for {name}: {e}")
                    result[name] = []
        return result

    async def get_model_for_task(
        self,
        task_type: str,
        project_id: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Get the provider and model for a task type.

        Checks in order:
        1. Project-specific assignment
        2. Global assignment
        3. Config defaults
        """
        # Check project-specific assignment first
        if project_id:
            stmt = select(ModelAssignment).where(
                ModelAssignment.project_id == project_id,
                ModelAssignment.task_type == task_type
            )
            result = await self.db.execute(stmt)
            assignment = result.scalars().first()
            if assignment:
                return assignment.provider, assignment.model

        # Check global assignment
        stmt = select(ModelAssignment).where(
            ModelAssignment.project_id.is_(None),
            ModelAssignment.task_type == task_type
        )
        result = await self.db.execute(stmt)
        assignment = result.scalars().first()
        if assignment:
            return assignment.provider, assignment.model

        # Fall back to config defaults
        if task_type == "knowledge":
            return settings.default_knowledge_provider, settings.default_knowledge_model
        elif task_type == "embedding":
            return settings.embedding_provider, settings.embedding_model
        else:
            raise ValueError(f"Unknown task type: {task_type}")

    async def set_model_assignment(
        self,
        task_type: str,
        provider: str,
        model: str,
        project_id: Optional[str] = None
    ) -> ModelAssignment:
        """Set or update a model assignment."""
        # Find existing assignment
        if project_id:
            stmt = select(ModelAssignment).where(
                ModelAssignment.project_id == project_id,
                ModelAssignment.task_type == task_type
            )
        else:
            stmt = select(ModelAssignment).where(
                ModelAssignment.project_id.is_(None),
                ModelAssignment.task_type == task_type
            )

        result = await self.db.execute(stmt)
        assignment = result.scalars().first()

        if assignment:
            assignment.provider = provider
            assignment.model = model
        else:
            assignment = ModelAssignment(
                project_id=project_id,
                task_type=task_type,
                provider=provider,
                model=model,
            )
            self.db.add(assignment)

        await self.db.flush()
        return assignment

    async def get_all_assignments(
        self,
        project_id: Optional[str] = None
    ) -> list[ModelAssignmentInfo]:
        """Get all model assignments, optionally filtered by project."""
        if project_id:
            stmt = select(ModelAssignment).where(
                (ModelAssignment.project_id == project_id) |
                (ModelAssignment.project_id.is_(None))
            )
        else:
            stmt = select(ModelAssignment)

        result = await self.db.execute(stmt)
        assignments = result.scalars().all()

        return [
            ModelAssignmentInfo(
                task_type=a.task_type,
                provider=a.provider,
                model=a.model,
                project_id=a.project_id,
            )
            for a in assignments
        ]

    def get_provider(self, name: str) -> Optional[LLMProvider]:
        """Get a provider instance by name."""
        return self.registry.get_provider(name)

    async def update_provider_config(
        self,
        provider_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        is_active: bool = True
    ) -> ProviderConfig:
        """Update provider configuration."""
        stmt = select(ProviderConfig).where(
            ProviderConfig.provider_name == provider_name
        )
        result = await self.db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            config = ProviderConfig(provider_name=provider_name)
            self.db.add(config)

        if api_key is not None:
            # Encrypt at rest; the column historically held plaintext (see
            # app.core.encryption / read sites use decrypt_if_encrypted).
            config.api_key_encrypted = encrypt_credential(api_key)
        if base_url is not None:
            config.base_url = base_url
        config.is_active = is_active

        await self.db.flush()

        # Update the provider in the registry
        provider = self.registry.get_provider(provider_name)
        if provider and api_key:
            provider.configure(api_key=api_key, base_url=base_url)

        return config
