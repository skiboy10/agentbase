"""
LLM Provider configuration API endpoints.
"""
import json
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.core.config import get_settings
from app.core.encryption import decrypt_if_encrypted, encrypt_credential
from app.models import APIKey, ProviderConfig, ModelAssignment
from app.providers.registry import get_registry
from app.providers.embedding_registry import get_embedding_registry

router = APIRouter()
settings = get_settings()


# Pydantic schemas
class ProviderConfigUpdate(BaseModel):
    """Provider configuration update."""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None
    disabled_models: Optional[list[str]] = None


class ProviderStatus(BaseModel):
    """Provider status response."""
    name: str
    display_name: str
    is_configured: bool
    is_active: bool
    is_healthy: bool = False
    available_models: list[str] = []
    disabled_models: list[str] = []
    base_url: Optional[str] = None
    requires_api_key: bool = True


class ModelInfo(BaseModel):
    """Model information."""
    id: str
    name: str
    provider: str
    context_window: int = 4096
    capabilities: list[str] = []


class ModelAssignmentRequest(BaseModel):
    """Model assignment request."""
    task_type: str  # "knowledge" or "embedding"
    provider: str
    model: str


class EmbeddingModelInfo(BaseModel):
    """Embedding model information."""
    id: str
    name: str
    provider: str
    dimensions: int
    max_input_tokens: int = 8192


class ModelAssignmentResponse(BaseModel):
    """Model assignment response."""
    task_type: str
    provider: str
    model: str
    is_global: bool = True


PROVIDER_DISPLAY_NAMES = {
    "ollama": "Ollama (Local)",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "grok": "Grok (xAI)",
    "google": "Google AI",
}


@router.get("", response_model=list[ProviderStatus])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all providers and their status."""
    registry = get_registry()
    providers = []

    for provider_name in ["ollama", "openai", "anthropic", "grok", "google"]:
        provider = registry.get_provider(provider_name)

        # Check if we have custom config in DB
        stmt = select(ProviderConfig).where(ProviderConfig.provider_name == provider_name)
        result = await db.execute(stmt)
        db_config = result.scalar_one_or_none()

        is_configured = provider.is_configured if provider else False
        is_active = db_config.is_active if db_config else is_configured
        base_url = None
        disabled_models = []

        # If is_active is explicitly False in DB, treat provider as not configured
        # This handles the case where user "deleted" an env-configured provider
        if db_config and not db_config.is_active:
            is_configured = False

        if provider_name == "ollama":
            base_url = settings.ollama_base_url

        # Parse disabled models from DB config
        if db_config and db_config.disabled_models:
            try:
                disabled_models = json.loads(db_config.disabled_models)
            except json.JSONDecodeError:
                disabled_models = []

        # Get available models if configured and active
        available_models = []
        is_healthy = False
        if provider and is_configured and is_active:
            try:
                models = await provider.list_models()
                available_models = [m.id for m in models]
                # If we successfully listed models, consider the provider healthy
                is_healthy = len(available_models) > 0
            except Exception:
                pass

        providers.append(ProviderStatus(
            name=provider_name,
            display_name=PROVIDER_DISPLAY_NAMES.get(provider_name, provider_name),
            is_configured=is_configured,
            is_active=is_active,
            is_healthy=is_healthy,
            available_models=available_models,
            disabled_models=disabled_models,
            base_url=base_url,
            requires_api_key=provider_name != "ollama",
        ))

    return providers


@router.get("/{provider_name}", response_model=ProviderStatus)
async def get_provider(
    provider_name: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get status and available models for a specific provider."""
    if provider_name not in ["ollama", "openai", "anthropic", "grok", "google"]:
        raise HTTPException(status_code=404, detail="Provider not found")

    registry = get_registry()
    provider = registry.get_provider(provider_name)

    # Check DB config
    stmt = select(ProviderConfig).where(ProviderConfig.provider_name == provider_name)
    result = await db.execute(stmt)
    db_config = result.scalar_one_or_none()

    is_configured = provider.is_configured if provider else False
    is_active = db_config.is_active if db_config else is_configured
    disabled_models = []

    # If is_active is explicitly False in DB, treat provider as not configured
    if db_config and not db_config.is_active:
        is_configured = False

    # Parse disabled models from DB config
    if db_config and db_config.disabled_models:
        try:
            disabled_models = json.loads(db_config.disabled_models)
        except json.JSONDecodeError:
            disabled_models = []

    # Get models and health
    available_models = []
    is_healthy = False
    if provider and is_configured and is_active:
        try:
            models = await provider.list_models()
            available_models = [m.id for m in models]
            is_healthy = await provider.health_check()
        except Exception:
            pass

    base_url = None
    if provider_name == "ollama":
        base_url = settings.ollama_base_url

    return ProviderStatus(
        name=provider_name,
        display_name=PROVIDER_DISPLAY_NAMES.get(provider_name, provider_name),
        is_configured=is_configured,
        is_active=is_active,
        is_healthy=is_healthy,
        available_models=available_models,
        disabled_models=disabled_models,
        base_url=base_url,
        requires_api_key=provider_name != "ollama",
    )


@router.put("/{provider_name}")
async def update_provider_config(
    provider_name: str,
    config: ProviderConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Update provider configuration (API key, base URL)."""
    if provider_name not in ["ollama", "openai", "anthropic", "grok", "google"]:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Get or create config
    stmt = select(ProviderConfig).where(ProviderConfig.provider_name == provider_name)
    result = await db.execute(stmt)
    db_config = result.scalar_one_or_none()

    if not db_config:
        db_config = ProviderConfig(provider_name=provider_name)
        db.add(db_config)

    # Update fields
    if config.api_key is not None:
        # Encrypt at rest; read sites use decrypt_if_encrypted (the column
        # historically held plaintext, hence the misleading name).
        db_config.api_key_encrypted = encrypt_credential(config.api_key)
        # Auto-activate provider when API key is added
        db_config.is_active = True
    if config.base_url is not None:
        db_config.base_url = config.base_url
    if config.is_active is not None:
        db_config.is_active = config.is_active
    if config.disabled_models is not None:
        db_config.disabled_models = json.dumps(config.disabled_models)

    await db.flush()

    # Update the runtime provider registry with new credentials
    # This allows providers configured via UI to work without restart
    registry = get_registry()
    if config.api_key is not None or config.base_url is not None:
        registry.configure_provider(
            provider_name,
            # config.api_key (if present) is the fresh plaintext from the
            # request; the stored column is encrypted and must be decrypted.
            api_key=config.api_key or decrypt_if_encrypted(db_config.api_key_encrypted),
            base_url=config.base_url or db_config.base_url,
        )

    return {"status": "updated", "provider": provider_name}


@router.delete("/{provider_name}")
async def delete_provider_config(
    provider_name: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Delete provider configuration (removes API key and settings).

    If the provider has a database config, it's deleted.
    If the provider is only configured via environment variables (no database record),
    we create a record with is_active=False to effectively disable it.
    """
    if provider_name not in ["ollama", "openai", "anthropic", "grok", "google"]:
        raise HTTPException(status_code=404, detail="Provider not found")

    registry = get_registry()

    # Find config
    stmt = select(ProviderConfig).where(ProviderConfig.provider_name == provider_name)
    result = await db.execute(stmt)
    db_config = result.scalar_one_or_none()

    if db_config:
        # Delete the existing database config
        await db.delete(db_config)
        await db.flush()

        # Remove from runtime registry (unless env var configured)
        settings = get_settings()
        env_key = getattr(settings, f"{provider_name}_api_key", None)
        if not env_key:
            registry.remove_provider(provider_name)

        return {"status": "deleted", "provider": provider_name}
    else:
        # Provider might be configured via environment variables
        # Check if the provider is actually configured
        provider = registry.get_provider(provider_name)

        if provider and provider.is_configured:
            # Provider is configured via env vars - create a disabled config to override
            new_config = ProviderConfig(
                provider_name=provider_name,
                is_active=False,
                api_key_encrypted=None,
            )
            db.add(new_config)
            await db.flush()
            return {"status": "disabled", "provider": provider_name}
        else:
            raise HTTPException(status_code=404, detail="Provider configuration not found")


@router.post("/{provider_name}/test")
async def test_provider_connection(
    provider_name: str,
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Test connection to a provider."""
    if provider_name not in ["ollama", "openai", "anthropic", "grok", "google"]:
        raise HTTPException(status_code=404, detail="Provider not found")

    registry = get_registry()
    provider = registry.get_provider(provider_name)

    if not provider:
        return {
            "status": "error",
            "provider": provider_name,
            "message": "Provider not initialized",
            "healthy": False,
        }

    if not provider.is_configured:
        return {
            "status": "error",
            "provider": provider_name,
            "message": "Provider not configured (missing API key)",
            "healthy": False,
        }

    try:
        is_healthy = await provider.health_check()
        models = await provider.list_models() if is_healthy else []

        return {
            "status": "success" if is_healthy else "error",
            "provider": provider_name,
            "healthy": is_healthy,
            "model_count": len(models),
            "message": "Connection successful" if is_healthy else "Health check failed",
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": provider_name,
            "healthy": False,
            "message": str(e),
        }


@router.get("/models/available", response_model=list[ModelInfo])
async def list_available_models(
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all available models across configured providers."""
    registry = get_registry()
    all_models = await registry.list_all_models()

    return [
        ModelInfo(
            id=m.id,
            name=m.name,
            provider=m.provider,
            context_window=m.context_window,
            capabilities=m.capabilities,
        )
        for m in all_models
    ]


@router.get("/embedding-models/available", response_model=list[EmbeddingModelInfo])
async def list_available_embedding_models(
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """List all available embedding models across configured providers."""
    registry = get_embedding_registry()
    all_models = await registry.list_all_embedding_models()

    return [
        EmbeddingModelInfo(
            id=m.id,
            name=m.name,
            provider=m.provider,
            dimensions=m.dimensions,
            max_input_tokens=m.max_input_tokens,
        )
        for m in all_models
    ]


@router.get("/models/assignments", response_model=list[ModelAssignmentResponse])
async def get_model_assignments(
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.READ)),
):
    """Get current model assignments (global or per project)."""
    # First check for project-specific assignments
    assignments = []

    if project_id:
        stmt = select(ModelAssignment).where(ModelAssignment.project_id == project_id)
        result = await db.execute(stmt)
        for assignment in result.scalars():
            assignments.append(ModelAssignmentResponse(
                task_type=assignment.task_type,
                provider=assignment.provider,
                model=assignment.model,
                is_global=False,
            ))

    # If no project assignments, return global defaults
    if not assignments:
        stmt = select(ModelAssignment).where(ModelAssignment.project_id.is_(None))
        result = await db.execute(stmt)
        for assignment in result.scalars():
            assignments.append(ModelAssignmentResponse(
                task_type=assignment.task_type,
                provider=assignment.provider,
                model=assignment.model,
                is_global=True,
            ))

    # If still no assignments, return config defaults
    if not assignments:
        assignments = [
            ModelAssignmentResponse(
                task_type="knowledge",
                provider=settings.default_knowledge_provider,
                model=settings.default_knowledge_model,
                is_global=True,
            ),
            ModelAssignmentResponse(
                task_type="embedding",
                provider=settings.embedding_provider,
                model=settings.embedding_model,
                is_global=True,
            ),
        ]
    else:
        # Ensure embedding assignment exists
        if not any(a.task_type == "embedding" for a in assignments):
            assignments.append(ModelAssignmentResponse(
                task_type="embedding",
                provider=settings.embedding_provider,
                model=settings.embedding_model,
                is_global=True,
            ))

    return assignments


@router.post("/models/assign")
async def assign_model(
    assignment: ModelAssignmentRequest,
    project_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.WRITE)),
):
    """Assign a model to a task type (globally or per project)."""
    # NOTE: Coding task type temporarily disabled - see BACKLOG.md
    valid_task_types = {"knowledge", "embedding", "question_generation", "answer_evaluation"}
    if assignment.task_type not in valid_task_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid task type. Must be one of: {', '.join(sorted(valid_task_types))}",
        )

    # Check if assignment exists
    stmt = select(ModelAssignment).where(
        ModelAssignment.task_type == assignment.task_type,
        ModelAssignment.project_id == project_id if project_id else ModelAssignment.project_id.is_(None)
    )
    result = await db.execute(stmt)
    existing = result.scalars().first()

    if existing:
        existing.provider = assignment.provider
        existing.model = assignment.model
    else:
        new_assignment = ModelAssignment(
            project_id=project_id,
            task_type=assignment.task_type,
            provider=assignment.provider,
            model=assignment.model,
        )
        db.add(new_assignment)

    await db.flush()

    return {
        "status": "assigned",
        "task_type": assignment.task_type,
        "provider": assignment.provider,
        "model": assignment.model,
        "project_id": project_id,
    }
