"""
Tests for reverse-proxy detection in app.core.auth._is_external_request.

Context: tunnels that terminate on the Docker host deliver traffic to the
backend from a host-local source IP (the Docker bridge gateway), which sits
inside TRUSTED_NETWORKS. The source-IP check alone therefore cannot
distinguish public tunnel traffic from localhost clients — both present the
same peer address.

The discriminator is forwarding headers: every reverse proxy sets
X-Forwarded-For (host-terminating tunnel proxies replace any
client-supplied value, so an attacker can never strip it), while direct
localhost/LAN clients never send one. A request carrying forwarding headers
that were NOT validated by SecretGatedProxyHeadersMiddleware must be
treated as external.
"""
import pytest
from starlette.requests import Request

import app.core.auth as core_auth
from app.core.auth import _is_external_request


class _Settings:
    """Minimal stand-in for app settings used by _is_external_request."""
    external_hostname = "tunnel.example.com"
    auth_token = None
    trusted_networks = "127.0.0.1/32,::1/128,192.168.0.0/16,172.16.0.0/12"
    trust_proxy = False


def _request(
    client_ip: str = "172.17.0.1",
    headers: dict | None = None,
    state: dict | None = None,
) -> Request:
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/mcp/",
        "query_string": b"",
        "scheme": "http",
        "headers": raw_headers,
        "client": (client_ip, 51234),
        "server": ("testserver", 80),
    }
    if state is not None:
        scope["state"] = state
    return Request(scope)


@pytest.fixture
def enforcing_settings(monkeypatch):
    """EXTERNAL_HOSTNAME set -> auth enforcement active."""
    settings = _Settings()
    monkeypatch.setattr(core_auth, "get_settings", lambda: settings)
    return settings


def test_direct_request_from_trusted_ip_is_internal(enforcing_settings):
    """Baseline unchanged: localhost/LAN clients with no forwarding headers."""
    assert _is_external_request(_request(client_ip="172.17.0.1")) is False


def test_direct_request_from_untrusted_ip_is_external(enforcing_settings):
    """Baseline unchanged: unknown source IPs require auth."""
    assert _is_external_request(_request(client_ip="203.0.113.9")) is True


def test_forwarded_for_from_trusted_ip_is_external(enforcing_settings):
    """The tunnel hole: the tunnel proxy connects from a trusted bridge IP
    but always adds X-Forwarded-For — that marks the request as external."""
    req = _request(
        client_ip="172.17.0.1",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert _is_external_request(req) is True


def test_rfc7239_forwarded_header_is_external(enforcing_settings):
    """The standard Forwarded header (RFC 7239) is detected too."""
    req = _request(
        client_ip="172.17.0.1",
        headers={"Forwarded": "for=203.0.113.9;proto=https"},
    )
    assert _is_external_request(req) is True


def test_forwarded_host_alone_is_external(enforcing_settings):
    req = _request(
        client_ip="172.17.0.1",
        headers={"X-Forwarded-Host": "tunnel.example.com"},
    )
    assert _is_external_request(req) is True


def test_secret_validated_proxy_falls_back_to_ip_check(enforcing_settings):
    """When SecretGatedProxyHeadersMiddleware validated the forward secret,
    it rewrites request.client to the real client IP and flags the scope;
    the IP check then decides. A LAN client via the trusted proxy stays
    internal even though XFF is present."""
    req = _request(
        client_ip="192.168.1.50",  # already rewritten by the middleware
        headers={"X-Forwarded-For": "192.168.1.50"},
        state={"proxy_headers_trusted": True},
    )
    assert _is_external_request(req) is False


def test_secret_validated_proxy_with_public_client_is_external(enforcing_settings):
    req = _request(
        client_ip="203.0.113.9",  # rewritten to the real public client
        headers={"X-Forwarded-For": "203.0.113.9"},
        state={"proxy_headers_trusted": True},
    )
    assert _is_external_request(req) is True


def test_dev_mode_ignores_forwarding_headers(monkeypatch):
    """No EXTERNAL_HOSTNAME and no AUTH_TOKEN -> nothing to protect."""
    settings = _Settings()
    settings.external_hostname = None
    settings.auth_token = None
    monkeypatch.setattr(core_auth, "get_settings", lambda: settings)
    req = _request(headers={"X-Forwarded-For": "203.0.113.9"})
    assert _is_external_request(req) is False


def test_trust_proxy_legacy_mode_uses_xff_ip(monkeypatch):
    """TRUST_PROXY=True deployments explicitly trust their proxy chain:
    XFF presence must not force external; the leftmost XFF IP decides."""
    settings = _Settings()
    settings.trust_proxy = True
    monkeypatch.setattr(core_auth, "get_settings", lambda: settings)
    internal = _request(
        client_ip="172.17.0.1",
        headers={"X-Forwarded-For": "192.168.1.50"},
    )
    external = _request(
        client_ip="172.17.0.1",
        headers={"X-Forwarded-For": "203.0.113.9"},
    )
    assert _is_external_request(internal) is False
    assert _is_external_request(external) is True
