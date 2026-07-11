"""
Platform API key authentication dependencies.

Provides FastAPI dependency functions for scope-based authorization.
Used by route handlers to enforce API key requirements.

Also provides contextvars-based auth for MCP tools, which don't have
access to FastAPI's request context.
"""
import contextvars
import hashlib
import ipaddress
from enum import Enum
from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models import APIKey
from app.services.auth_service import AuthService

# ContextVar for passing auth state into MCP tools (set by middleware)
# Values: None (no auth), "auth_token" (global token), or APIKey instance
_current_auth: contextvars.ContextVar[Optional[object]] = contextvars.ContextVar(
    "current_auth", default=None
)

# Sentinel for AUTH_TOKEN-authenticated requests (full access)
AUTH_TOKEN_SENTINEL = "auth_token"


def set_current_auth(auth: Optional[object]) -> contextvars.Token:
    """Set the current request's auth state (called by middleware).

    Returns the ContextVar token so callers that own a request scope can
    reset_current_auth() afterwards and avoid leaking auth into reused tasks.
    """
    return _current_auth.set(auth)


def reset_current_auth(token: contextvars.Token) -> None:
    """Restore the auth state captured by a set_current_auth() call."""
    _current_auth.reset(token)


def get_current_auth() -> Optional[object]:
    """Get the current request's auth state (used by MCP tools)."""
    return _current_auth.get()


def check_mcp_scope(required_scope: "Scope") -> None:
    """
    Check scope for MCP tool execution. Raises ValueError if insufficient.

    Call this at the top of any MCP tool that performs write operations.
    Read operations can skip this if you want MCP read access to be open
    once past the middleware token check.
    """
    auth = get_current_auth()

    # AUTH_TOKEN mode: full access
    if auth == AUTH_TOKEN_SENTINEL:
        return

    # Valid API key: check scope
    if isinstance(auth, APIKey):
        if _has_scope(auth, required_scope):
            return
        raise ValueError(f"Insufficient scope. Required: '{required_scope.value}'")

    # No auth context — contextvar didn't propagate (MCP Streamable HTTP transport
    # processes tool calls in separate async contexts). The _MCPAuthWrapper in
    # main.py already gates the initial MCP HTTP connection:
    #   - External requests without a valid Bearer token are rejected
    #   - Internal/LAN requests get AUTH_TOKEN_SENTINEL
    # Any tool call that reaches here has already passed that connection-level
    # check, so it's safe to allow regardless of which auth settings are
    # configured (dev mode, EXTERNAL_HOSTNAME-only, AUTH_TOKEN, or both).
    return


class Scope(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


# Scope hierarchy: higher scopes include lower ones
# e.g., an "admin" key can do everything "read" and "write" can do
SCOPE_HIERARCHY = {
    Scope.READ: {Scope.READ, Scope.WRITE, Scope.ADMIN},
    Scope.WRITE: {Scope.WRITE, Scope.ADMIN},
    Scope.ADMIN: {Scope.ADMIN},
}


def _has_scope(api_key: APIKey, required: Scope) -> bool:
    """Check if key has the required scope (respecting hierarchy)."""
    allowed = SCOPE_HIERARCHY[required]
    return any(scope in allowed for scope in api_key.scopes)


def _get_trusted_networks(settings) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    """Parse TRUSTED_NETWORKS setting into a list of network objects."""
    networks = []
    for cidr in settings.trusted_networks.split(","):
        cidr = cidr.strip()
        if cidr:
            try:
                networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError:
                pass  # Ignore malformed entries rather than crashing
    return networks


def _get_client_ip(request: Request, settings) -> str:
    """
    Resolve the real client IP address.

    NOTE: main.py mounts SecretGatedProxyHeadersMiddleware (#49), which
    rewrites request.client based on X-Forwarded-For ONLY when the request
    carries a matching X-Internal-Forward-Secret header. So:
      - Proxied requests through nginx → request.client.host = real client IP
      - Direct connections (no proxy or missing/bad secret) → real TCP peer

    TRUST_PROXY remains a fallback that reads XFF directly from the raw
    header. Leave it False in any deployment that uses the secret-gated
    middleware; True is only for setups with additional proxy hops not
    covered by the middleware.
    """
    if settings.trust_proxy:
        forwarded_for = request.headers.get("x-forwarded-for", "")
        if forwarded_for:
            # Take only the first (leftmost) address — that is the original client
            candidate = forwarded_for.split(",")[0].strip()
            if candidate:
                return candidate
    # Use the TCP source address — already rewritten by
    # SecretGatedProxyHeadersMiddleware in proxy deployments when the
    # X-Internal-Forward-Secret header validated, raw TCP peer otherwise.
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"  # Safe default: treat as trusted if we cannot determine


# Headers that mean a reverse proxy (or a client pretending to be one) sits
# between the real client and the backend. Every reverse proxy in common
# tunnel setups sets X-Forwarded-For, and host-terminating tunnel proxies
# replace any client-supplied value with the real peer address — so tunnel
# traffic can never arrive without it and external clients cannot strip it.
# Direct localhost/LAN clients never send any of these; sending one can only
# downgrade their trust, so there is no spoofing route INTO trust.
_FORWARDING_HEADERS = (
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
    "forwarded",
)


def _is_proxied_without_secret(request: Request) -> bool:
    """True when the request carries forwarding headers that were NOT
    validated by SecretGatedProxyHeadersMiddleware (which sets the
    proxy_headers_trusted scope flag and rewrites request.client, letting
    the normal source-IP check decide)."""
    if request.scope.get("state", {}).get("proxy_headers_trusted"):
        return False
    return any(header in request.headers for header in _FORWARDING_HEADERS)


def _is_external_request(request: Request) -> bool:
    """
    Determine whether a request originates from outside the trusted network.

    Returns True  → external, authentication required.
    Returns False → internal/LAN, open access.

    Auth enforcement is only active when EXTERNAL_HOSTNAME or AUTH_TOKEN is
    configured.  In a plain dev environment (neither set) every request is
    treated as internal so the system works out of the box.

    The decision is based on the source IP address, not the Host header.
    The Host header is trivially spoofable (any client can send
    "Host: localhost") whereas the TCP source address cannot be forged for a
    connection that actually reaches the server.

    Source IP alone cannot see through tunnels that terminate on the Docker
    host (e.g. Cloudflare Tunnel or a mesh-VPN funnel): their traffic
    reaches the backend from the bridge gateway, the same trusted source IP
    localhost clients present. Proxied traffic is therefore detected by its
    forwarding headers and treated as external unless the proxy
    authenticated itself via the forward secret.
    """
    settings = get_settings()

    # Dev-mode shortcut: if neither EXTERNAL_HOSTNAME nor AUTH_TOKEN is
    # configured, there is no external surface to protect.
    if not settings.external_hostname and not settings.auth_token:
        return False

    # Tunnel-proxied traffic (identified by forwarding headers without the
    # forward secret) is external regardless of its host-local source IP.
    # TRUST_PROXY deployments explicitly trust their proxy chain instead:
    # there the leftmost X-Forwarded-For IP feeds the check below.
    if not settings.trust_proxy and _is_proxied_without_secret(request):
        return True

    client_ip = _get_client_ip(request, settings)

    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        # Unparseable IP — treat as external to be safe
        return True

    # Unwrap IPv4-mapped IPv6 addresses (e.g. ::ffff:127.0.0.1 → 127.0.0.1)
    # so they match IPv4 CIDR entries in the trusted networks list.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped

    trusted = _get_trusted_networks(settings)
    for network in trusted:
        if addr in network:
            return False  # Trusted network → internal

    return True  # Not in any trusted range → external


async def get_api_key_from_request(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[APIKey]:
    """
    Extract and validate API key from the request.

    Checks request.state first (set by middleware when AUTH_TOKEN is active),
    then falls back to parsing the Authorization header directly.

    Returns None if no auth header is present (allows bootstrap mode).
    """
    # If middleware already validated (AUTH_TOKEN mode), use that
    if hasattr(request.state, "api_key") and request.state.api_key is not None:
        return request.state.api_key

    # If middleware stored AUTH_TOKEN match, grant full access (no APIKey object needed)
    if hasattr(request.state, "auth_method") and request.state.auth_method == "auth_token":
        return None  # Signal: authenticated via AUTH_TOKEN, bypass scope checks

    # If middleware pre-computed the hash (API key mode, no AUTH_TOKEN), use it
    if hasattr(request.state, "api_key_hash"):
        service = AuthService(db)
        return await service.validate_key_by_hash(request.state.api_key_hash)

    # Fallback: parse Bearer token from header directly
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header[7:]
    service = AuthService(db)
    return await service.validate_key(token)


def require_scope(scope: Scope):
    """
    Dependency factory that enforces API key scope requirements.

    Local/LAN requests always pass through without an API key — this
    ensures the admin can always manage the system from the local network
    (create keys, configure providers, etc.).

    External requests (via tunnel) always require a valid API key with
    sufficient scope.
    """
    async def _check_scope(
        request: Request,
        db: AsyncSession = Depends(get_db),
        api_key: Optional[APIKey] = Depends(get_api_key_from_request),
    ) -> Optional[APIKey]:
        settings = get_settings()

        # AUTH_TOKEN mode: if middleware validated via AUTH_TOKEN, full access
        if hasattr(request.state, "auth_method") and request.state.auth_method == "auth_token":
            return None

        # If we have a valid API key, check scope
        if api_key is not None:
            if not _has_scope(api_key, scope):
                raise HTTPException(
                    status_code=403,
                    detail=f"Insufficient scope. Required: '{scope.value}'",
                )
            return api_key

        # No API key provided — local/LAN always allowed, external requires key
        if not _is_external_request(request):
            return None  # Local/LAN access — open access for admin

        # External request without a key — require auth
        raise HTTPException(
            status_code=401,
            detail="API key required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _check_scope
