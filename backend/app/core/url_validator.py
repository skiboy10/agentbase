"""
SSRF protection — URL validation module.

Validates URLs before server-side fetching to prevent Server-Side Request
Forgery (SSRF) attacks. Attackers could otherwise probe internal services
like Postgres, Docker host networks, or cloud metadata endpoints.

Usage:
    from app.core.url_validator import validate_url

    safe_url = validate_url(user_supplied_url)  # raises ValueError if unsafe
"""

import ipaddress
import socket
from typing import Optional
from urllib.parse import urlparse

import structlog

from app.core.config import get_settings

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Blocked IP ranges (RFC-reserved, private, and cloud-metadata ranges)
# ---------------------------------------------------------------------------

_BLOCKED_NETWORKS_V4 = [
    ipaddress.ip_network("0.0.0.0/8"),         # "This" network
    ipaddress.ip_network("10.0.0.0/8"),         # RFC 1918 private
    ipaddress.ip_network("100.64.0.0/10"),      # Shared address space (RFC 6598)
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local / AWS metadata
    ipaddress.ip_network("172.16.0.0/12"),      # RFC 1918 private
    ipaddress.ip_network("192.0.0.0/24"),       # IETF protocol assignments
    ipaddress.ip_network("192.168.0.0/16"),     # RFC 1918 private
    ipaddress.ip_network("198.18.0.0/15"),      # Network benchmark testing
    ipaddress.ip_network("198.51.100.0/24"),    # TEST-NET-2 (docs/examples)
    ipaddress.ip_network("203.0.113.0/24"),     # TEST-NET-3 (docs/examples)
    ipaddress.ip_network("224.0.0.0/4"),        # Multicast
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
    ipaddress.ip_network("255.255.255.255/32"), # Broadcast
]

_BLOCKED_NETWORKS_V6 = [
    ipaddress.ip_network("::1/128"),            # Loopback
    ipaddress.ip_network("::/128"),             # Unspecified
    ipaddress.ip_network("fc00::/7"),           # Unique local (ULA) — RFC 4193
    ipaddress.ip_network("fe80::/10"),          # Link-local
    ipaddress.ip_network("ff00::/8"),           # Multicast
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6
    ipaddress.ip_network("64:ff9b::/96"),       # IPv4/IPv6 translation
    ipaddress.ip_network("100::/64"),           # Discard prefix
]


def _is_ip_blocked(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True if the resolved IP falls into any blocked range."""
    if isinstance(addr, ipaddress.IPv4Address):
        return any(addr in net for net in _BLOCKED_NETWORKS_V4)
    elif isinstance(addr, ipaddress.IPv6Address):
        # Unwrap IPv4-mapped IPv6 addresses (::ffff:192.168.x.x) before checking
        if addr.ipv4_mapped is not None:
            return _is_ip_blocked(addr.ipv4_mapped)
        return any(addr in net for net in _BLOCKED_NETWORKS_V6)
    return True  # Block anything we can't classify


def _resolve_host(hostname: str) -> list[str]:
    """
    Resolve hostname to a list of IP address strings.

    Uses socket.getaddrinfo so we follow the same resolution path the HTTP
    client would use (respects /etc/hosts, ndots, search domains, etc.).

    Raises ValueError if resolution fails.
    """
    try:
        # AF_UNSPEC covers both IPv4 and IPv6 results
        info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve hostname '{hostname}': {exc}") from exc

    # getaddrinfo returns (family, type, proto, canonname, sockaddr)
    # sockaddr is (ip, port) for IPv4 or (ip, port, flowinfo, scope) for IPv6
    return [entry[4][0] for entry in info]


def validate_url(url: str) -> str:
    """
    Validate a URL is safe for server-side fetching.

    Checks performed (in order):
    1. URL must use http or https scheme
    2. URL must have a non-empty hostname
    3. The hostname resolves to at least one IP
    4. Every resolved IP must be a public, routable address

    Returns the original url string unchanged if it passes all checks.
    Raises ValueError with a user-safe message if anything is suspicious.

    The check is skipped entirely when SSRF_PROTECTION_ENABLED=false in
    settings (useful for local development scanning of localhost services).
    """
    settings = get_settings()

    if not settings.ssrf_protection_enabled:
        logger.debug("SSRF protection disabled, skipping URL validation", url=url)
        return url

    # --- 1. Scheme check ---
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Malformed URL: {exc}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ValueError(
            f"URL scheme '{scheme}' is not allowed. Only http and https are permitted."
        )

    # --- 2. Hostname check ---
    hostname = parsed.hostname  # urlparse normalises brackets for IPv6
    if not hostname:
        raise ValueError("URL must include a hostname.")

    # --- 3. Handle IP-literal URLs (e.g. http://127.0.0.1/ or http://[::1]/) ---
    # urlparse already strips [ ] from IPv6 literals
    try:
        literal_ip = ipaddress.ip_address(hostname)
        if _is_ip_blocked(literal_ip):
            raise ValueError(
                f"Requests to '{hostname}' are not allowed (reserved/internal address)."
            )
        # IP literal is public — no DNS resolution needed
        logger.debug("URL validated (IP literal)", url=url, ip=str(literal_ip))
        return url
    except ValueError as e:
        # Re-raise our own SSRF errors immediately
        if "are not allowed" in str(e):
            raise
        # Otherwise it's not a valid IP literal — treat as a hostname and resolve below

    # --- 4. Decimal / octal / hex integer IP encoding check ---
    # e.g. http://2130706433/ == http://127.0.0.1/
    # Python's ipaddress module handles these non-standard forms too
    try:
        # Attempt integer/non-dotted parsing
        candidate = ipaddress.ip_address(int(hostname))
        if _is_ip_blocked(candidate):
            raise ValueError(
                f"Requests to '{hostname}' are not allowed (reserved/internal address)."
            )
        return url
    except (ValueError, TypeError):
        pass  # Not an integer-encoded IP — proceed to DNS resolution

    # --- 5. DNS resolution (catches e.g. evil.com → 127.0.0.1) ---
    resolved_ips = _resolve_host(hostname)
    if not resolved_ips:
        raise ValueError(f"Could not resolve '{hostname}' to any IP address.")

    for ip_str in resolved_ips:
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            # Should not happen since getaddrinfo returns valid IPs, but be safe
            raise ValueError(f"Unexpected address format from DNS resolution: '{ip_str}'")

        if _is_ip_blocked(addr):
            logger.warning(
                "SSRF attempt blocked",
                url=url,
                hostname=hostname,
                resolved_ip=ip_str,
            )
            raise ValueError(
                f"Requests to '{hostname}' are not allowed (resolves to a reserved/internal address)."
            )

    logger.debug("URL validated", url=url, resolved_ips=resolved_ips)
    return url


# Hosts permitted for the YouTube source type (#133). The channel URL is the
# only user-controlled host in YouTube ingestion; per-video watch URLs are
# constructed server-side from video IDs, so they need no host check.
# Channel URLs only ever live on youtube.com hosts; youtu.be is a watch-URL
# shortener and is never a channel, so it is intentionally excluded.
_YOUTUBE_HOSTS = frozenset({
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
})


def validate_youtube_channel_url(url: str) -> str:
    """Validate a YouTube channel URL: host allowlist + SSRF check.

    Raises ValueError if the URL is not an http(s) YouTube URL or fails the
    standard SSRF resolution check. Returns the URL unchanged on success.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Malformed URL: {exc}") from exc

    if (parsed.scheme or "").lower() not in ("http", "https"):
        raise ValueError("Channel URL must use http or https.")

    host = (parsed.hostname or "").lower().rstrip(".")  # tolerate FQDN trailing dot
    if host not in _YOUTUBE_HOSTS:
        raise ValueError(
            f"'{host or url}' is not a recognised YouTube URL. "
            "Provide a channel URL like https://www.youtube.com/@channelname"
        )

    # Reuse the standard SSRF resolution check (youtube.com is public, so this
    # passes — but it guards against DNS tricks resolving to internal ranges).
    return validate_url(url)


def validate_url_safe(url: str) -> Optional[str]:
    """
    Non-raising variant of validate_url.

    Returns the URL string if it passes validation, or None if it is unsafe
    or malformed.  Logs a warning on rejection.

    Useful when iterating over a list of discovered URLs and you want to
    silently skip unsafe ones rather than aborting the whole scan.
    """
    try:
        return validate_url(url)
    except ValueError as exc:
        logger.warning("Skipping unsafe URL", url=url, reason=str(exc))
        return None
