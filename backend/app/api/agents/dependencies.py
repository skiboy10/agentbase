"""
Security dependencies for Agent API endpoints.

Provides internal vs external request detection based on Host header.
"""

from fastapi import Request

from app.core.config import get_settings


def is_external_request(request: Request) -> bool:
    """
    Check if request arrives via the external tunnel hostname.

    Compares the Host header (or X-Forwarded-Host) against the configured
    EXTERNAL_HOSTNAME. If no external hostname is configured, all requests
    are treated as internal.
    """
    settings = get_settings()
    if not settings.external_hostname:
        return False
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    hostname = host.split(":")[0]
    return hostname == settings.external_hostname
