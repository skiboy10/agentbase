"""
Secret-gated proxy headers middleware (#49).

Replaces uvicorn's ProxyHeadersMiddleware(trusted_hosts="*"), which trusted
X-Forwarded-For from any client. With trusted_hosts="*", an attacker reaching
the backend port directly (Tailscale, LAN, container exec) could send
`X-Forwarded-For: 127.0.0.1` and have request.client.host rewritten to a
trusted-network IP, bypassing the IP-based auth check.

Instead, this middleware only honors X-Forwarded-For / X-Forwarded-Proto when
the request also carries an X-Internal-Forward-Secret header matching the
shared secret set in both nginx and backend. When the setting is unset, the
middleware no-ops (so local dev/test still works), with a startup warning.
"""

from __future__ import annotations

import hmac
from typing import Optional

import structlog
from starlette.types import ASGIApp, Receive, Scope, Send

logger = structlog.get_logger()


_VALID_SCHEMES = {"http", "https", "ws", "wss"}


class SecretGatedProxyHeadersMiddleware:
    """Trust X-Forwarded-For only when a shared-secret header matches."""

    def __init__(self, app: ASGIApp, secret: Optional[str]) -> None:
        self.app = app
        self._secret_bytes: Optional[bytes] = (
            secret.encode("utf-8") if secret else None
        )
        if not secret:
            logger.warning(
                "INTERNAL_FORWARD_SECRET unset — proxy headers will be ignored. "
                "Safe for local dev. INSECURE for any deployment that exposes "
                "the backend port externally (Tailscale, Cloudflare Tunnel, LAN)."
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)

        if self._secret_bytes is None:
            return await self.app(scope, receive, send)

        headers = dict(scope["headers"])
        presented = headers.get(b"x-internal-forward-secret", b"")
        # Constant-time compare — hmac.compare_digest tolerates unequal
        # lengths without leaking timing information.
        if not hmac.compare_digest(presented, self._secret_bytes):
            return await self.app(scope, receive, send)

        # Tell downstream auth checks the forwarding headers on this request
        # came from our own proxy: _is_external_request() skips its
        # proxied-without-secret rejection and decides on the rewritten
        # client IP instead.
        scope.setdefault("state", {})["proxy_headers_trusted"] = True

        if b"x-forwarded-proto" in headers:
            xfp = headers[b"x-forwarded-proto"].decode("latin-1").strip().lower()
            if xfp in _VALID_SCHEMES:
                if scope["type"] == "websocket":
                    scope["scheme"] = xfp.replace("http", "ws")
                else:
                    scope["scheme"] = xfp

        if b"x-forwarded-for" in headers:
            xff = headers[b"x-forwarded-for"].decode("latin-1")
            # Leftmost = original client. nginx appends the upstream IP to
            # any pre-existing chain, so reading from the left is correct.
            first = xff.split(",")[0].strip()
            if first:
                # Preserve port from the TCP peer tuple if present.
                client = scope.get("client")
                port = client[1] if client else 0
                scope["client"] = (first, port)

        return await self.app(scope, receive, send)
