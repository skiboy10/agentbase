"""
Bearer token authentication middleware.

Supports two authentication methods:
1. AUTH_TOKEN (global lockdown) — single shared token via env var
2. Platform API keys (pk_ prefix) — scoped keys stored in database

When AUTH_TOKEN is set, the middleware is the absolute gate: it validates
the token against AUTH_TOKEN first, then falls back to API key DB lookup.
When AUTH_TOKEN is not set, the middleware validates the key and stores the
resolved APIKey object on request.state for downstream scope-checking dependencies.
"""
import secrets as secrets_mod

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import structlog

from app.core.config import get_settings
from app.core.database import async_session_maker
from app.core.auth import set_current_auth, AUTH_TOKEN_SENTINEL

logger = structlog.get_logger()

# Paths that never require authentication
EXEMPT_PATHS = {"/health", "/", "/docs", "/redoc", "/openapi.json"}

# Path prefixes that require authentication when AUTH_TOKEN is set
PROTECTED_PREFIXES = ("/api/", "/mcp")


class BearerTokenMiddleware(BaseHTTPMiddleware):
    """Bearer token + API key authentication for API routes."""

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        path = request.url.path

        # Check if path is exempt
        if path in EXEMPT_PATHS:
            return await call_next(request)

        # Check if path requires authentication
        requires_auth = any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
        if not requires_auth:
            return await call_next(request)

        # Parse Bearer token
        auth_header = request.headers.get("Authorization", "")
        has_bearer = auth_header.startswith("Bearer ")
        token = auth_header[7:] if has_bearer else None

        if settings.auth_token:
            # === AUTH_TOKEN mode (global lockdown) ===
            # Middleware is the absolute gate — must validate here.
            return await self._auth_token_mode(request, call_next, token, settings)
        else:
            # === API key only mode ===
            # Middleware validates and stores the resolved APIKey for downstream dependencies.
            return await self._api_key_mode(request, call_next, token)

    async def _auth_token_mode(self, request, call_next, token, settings):
        """AUTH_TOKEN is set: middleware must fully validate."""
        # Trusted-network bypass: internal containers skip the global token gate
        from app.core.auth import _is_external_request
        if not _is_external_request(request):
            request.state.auth_method = "auth_token"
            set_current_auth(AUTH_TOKEN_SENTINEL)
            return await call_next(request)

        if token is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Check 1: Does it match the global AUTH_TOKEN? (timing-safe)
        if secrets_mod.compare_digest(token, settings.auth_token):
            request.state.auth_method = "auth_token"
            set_current_auth(AUTH_TOKEN_SENTINEL)
            return await call_next(request)

        # Check 2: Is it a valid platform API key? (DB lookup)
        api_key = await self._validate_api_key(token)
        if api_key is not None:
            request.state.api_key = api_key
            request.state.auth_method = "api_key"
            set_current_auth(api_key)
            return await call_next(request)

        # Neither matched
        logger.warning("Invalid auth attempt", path=request.url.path)
        return JSONResponse(
            status_code=401,
            content={"detail": "Invalid authentication token"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    async def _api_key_mode(self, request, call_next, token):
        """No AUTH_TOKEN: validate token and store result on request.state."""
        if token is not None:
            # Validate the key against the DB (Argon2-aware).
            # Store the resolved APIKey object directly so downstream
            # require_scope() dependencies can use it without a second DB
            # round-trip.  This replaces the old SHA-256 pre-hash approach
            # which is incompatible with Argon2 (hashes cannot be looked up
            # by value — they must be verified against a candidate row).
            api_key = await self._validate_api_key(token)
            if api_key is not None:
                request.state.api_key = api_key
                set_current_auth(api_key)
        else:
            # No token provided — grant full access for internal/LAN requests
            # so MCP tools (which use check_mcp_scope via contextvars, not
            # FastAPI's require_scope dependency) can authorize write ops.
            from app.core.auth import _is_external_request
            if not _is_external_request(request):
                set_current_auth(AUTH_TOKEN_SENTINEL)
        # Pass through — let endpoint require_scope() dependencies decide
        return await call_next(request)

    async def _validate_api_key(self, token: str):
        """Validate a platform API key against the database."""
        from app.services.auth_service import AuthService

        async with async_session_maker() as session:
            try:
                service = AuthService(session)
                api_key = await service.validate_key(token)
                return api_key
            except Exception as e:
                logger.error("API key validation error", error=str(e))
                return None
