"""Auth API routes for platform API key management."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.auth import Scope, require_scope
from app.core.database import get_db
from app.models import APIKey
from app.services.auth_service import AuthService

from .schemas import APIKeyCreate, APIKeyResponse, APIKeyCreateResponse, BootstrapKeyCreate

logger = structlog.get_logger()

router = APIRouter()


@router.get(
    "/auth/keys",
    response_model=list[APIKeyResponse],
    summary="List all platform API keys",
)
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.ADMIN)),
):
    """List all platform API keys. Key hashes are never returned."""
    service = AuthService(db)
    keys = await service.list_keys()
    return keys


@router.post(
    "/auth/keys",
    response_model=APIKeyCreateResponse,
    status_code=201,
    summary="Create a new platform API key",
)
async def create_api_key(
    data: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.ADMIN)),
):
    """
    Create a new platform API key.

    The full key is returned once in the response. It cannot be retrieved again.
    """
    service = AuthService(db)
    try:
        api_key, plain_key = await service.create_key(
            name=data.name,
            scopes=data.scopes,
            rate_limit_rpm=data.rate_limit_rpm,
            expires_at=data.expires_at,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return APIKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        rate_limit_rpm=api_key.rate_limit_rpm,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        api_key=plain_key,
    )


@router.delete(
    "/auth/keys/{key_id}",
    summary="Revoke a platform API key",
)
async def revoke_api_key(
    key_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: Optional[APIKey] = Depends(require_scope(Scope.ADMIN)),
):
    """Soft-revoke an API key. The key becomes inactive but the record is kept."""
    service = AuthService(db)
    revoked = await service.revoke_key(key_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked", "id": key_id}


@router.post(
    "/auth/bootstrap",
    response_model=APIKeyCreateResponse,
    status_code=201,
    summary="Create first admin API key (bootstrap)",
)
async def bootstrap_api_key(
    data: BootstrapKeyCreate = BootstrapKeyCreate(),
    db: AsyncSession = Depends(get_db),
):
    """
    Bootstrap the first platform API key.

    No authentication required. Self-disables once any active API key exists
    (returns 409). This is the only way to create the initial admin key for
    machine-to-machine access.

    The full key is returned once in the response. Store it securely.
    """
    service = AuthService(db)

    has_keys = await service.has_any_active_keys()
    if has_keys:
        raise HTTPException(
            status_code=409,
            detail="Bootstrap disabled — active API keys already exist. Use an admin key to create more.",
        )

    try:
        api_key, plain_key = await service.create_key(
            name=data.name,
            scopes=["admin"],
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        "Bootstrap API key created",
        key_id=api_key.id,
        name=api_key.name,
    )

    return APIKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        rate_limit_rpm=api_key.rate_limit_rpm,
        expires_at=api_key.expires_at,
        last_used_at=api_key.last_used_at,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        api_key=plain_key,
    )
