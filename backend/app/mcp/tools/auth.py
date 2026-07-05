"""
MCP Tools for Authentication Bootstrap

Provides the agentbase_bootstrap_api_key tool for creating the first admin API key
when no keys exist yet — enabling machine-to-machine onboarding.
"""

from typing import Optional
import structlog

from app.mcp.server import mcp
from app.core.database import async_session_maker
from app.services.auth_service import AuthService

logger = structlog.get_logger()


@mcp.tool(
    description=(
        "Create the first admin API key (no auth required). "
        "Self-disables once any active key exists. Store the returned key securely."
    ),
    annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
)
async def agentbase_bootstrap_api_key(name: Optional[str] = "Bootstrap Admin Key") -> dict:
    """Bootstrap the first API key. Only works when no keys exist."""
    async with async_session_maker() as db:
        service = AuthService(db)

        has_keys = await service.has_any_active_keys()
        if has_keys:
            return {
                "error": "Bootstrap disabled — active API keys already exist. "
                "Use an admin key to create more.",
            }

        key_name = name if name else "Bootstrap Admin Key"
        try:
            api_key, plain_key = await service.create_key(
                name=key_name,
                scopes=["admin"],
            )
        except ValueError as e:
            return {"error": str(e)}

        logger.info(
            "Bootstrap API key created via MCP",
            key_id=api_key.id,
            name=api_key.name,
        )

        return {
            "status": "created",
            "id": api_key.id,
            "name": api_key.name,
            "key_prefix": api_key.key_prefix,
            "scopes": api_key.scopes,
            "api_key": plain_key,
            "message": "Store this key securely — it will not be shown again",
        }
