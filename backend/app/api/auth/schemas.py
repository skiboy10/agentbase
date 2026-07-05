"""Pydantic schemas for auth API endpoints."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class APIKeyCreate(BaseModel):
    name: str = Field(..., max_length=255, description="Human-readable name for this key")
    scopes: list[str] = Field(
        default=["read"],
        description="Permission scopes: read, write, admin",
    )
    rate_limit_rpm: Optional[int] = Field(
        default=None,
        description="Optional rate limit in requests per minute",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Optional expiration datetime (UTC)",
    )


class APIKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    scopes: list[str]
    rate_limit_rpm: Optional[int]
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class APIKeyCreateResponse(APIKeyResponse):
    """Only returned on creation — includes the full key."""
    api_key: str
    message: str = "Store this key securely — it will not be shown again"


class BootstrapKeyCreate(BaseModel):
    name: str = Field(
        default="Bootstrap Admin Key",
        max_length=255,
        description="Human-readable name for the bootstrap key",
    )
