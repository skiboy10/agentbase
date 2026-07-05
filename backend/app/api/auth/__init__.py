"""
Auth API router package.

Provides platform API key management endpoints.
"""
from fastapi import APIRouter

from .routes import router as auth_router
from .schemas import APIKeyCreate, APIKeyResponse, APIKeyCreateResponse, BootstrapKeyCreate

router = APIRouter()
router.include_router(auth_router, tags=["auth"])

__all__ = [
    "router",
    "APIKeyCreate", "APIKeyResponse", "APIKeyCreateResponse", "BootstrapKeyCreate",
]
