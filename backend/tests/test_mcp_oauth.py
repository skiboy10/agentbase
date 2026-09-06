"""MCP OAuth 2.1 discovery + PKCE (Gemini Spark Connected Apps)."""
import base64
import hashlib

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


@pytest.fixture
def oauth_client():
    from app.main import app
    return app


@pytest.mark.asyncio
async def test_protected_resource_metadata(oauth_client):
    transport = ASGITransport(app=oauth_client)
    async with AsyncClient(transport=transport, base_url="https://mcp.example.test") as c:
        r = await c.get("/.well-known/oauth-protected-resource")
        r2 = await c.get("/.well-known/oauth-protected-resource/mcp")
    assert r.status_code == 200
    assert r2.status_code == 200
    body = r.json()
    assert body["resource"].endswith("/mcp")
    assert body["authorization_servers"]
    assert "header" in body["bearer_methods_supported"]


@pytest.mark.asyncio
async def test_authorization_server_metadata_has_dcr(oauth_client):
    transport = ASGITransport(app=oauth_client)
    async with AsyncClient(transport=transport, base_url="https://mcp.example.test") as c:
        r = await c.get("/.well-known/oauth-authorization-server")
    assert r.status_code == 200
    body = r.json()
    assert body["registration_endpoint"].endswith("/api/oauth/register")
    assert "S256" in body["code_challenge_methods_supported"]
    assert "none" in body["token_endpoint_auth_methods_supported"]


@pytest.mark.asyncio
async def test_dcr_pkce_roundtrip(oauth_client):
    from types import SimpleNamespace

    verifier = "a" * 64
    challenge = _challenge(verifier)
    redirect = "https://oauth-redirect.googleusercontent.com/r/demo"
    fake_key = SimpleNamespace(is_active=True)

    class _Svc:
        def __init__(self, db):
            pass

        async def validate_key(self, token):
            return fake_key if token == "pk_test_spark" else None

    transport = ASGITransport(app=oauth_client)
    async with AsyncClient(transport=transport, base_url="https://mcp.example.test") as c:
        reg = await c.post(
            "/api/oauth/register",
            json={
                "client_name": "Google",
                "redirect_uris": [redirect, "https://example.com/cb"],
                "token_endpoint_auth_method": "none",
            },
        )
        assert reg.status_code == 201
        client_id = reg.json()["client_id"]
        assert "client_secret" not in reg.json()

        page = await c.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect,
                "state": "st",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": "https://mcp.example.test/mcp",
            },
        )
        assert page.status_code == 200
        assert "Connect Gemini" in page.text

        with patch("app.api.mcp_oauth.async_session_maker") as maker, \
             patch("app.api.mcp_oauth.AuthService", _Svc):
            maker.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            maker.return_value.__aexit__ = AsyncMock(return_value=False)
            consent = await c.post(
                "/oauth/authorize",
                params={
                    "client_id": client_id,
                    "redirect_uri": redirect,
                    "state": "st",
                    "code_challenge": challenge,
                },
                data={"api_key": "pk_test_spark", "decision": "allow"},
                follow_redirects=False,
            )
        assert consent.status_code == 302
        loc = consent.headers["location"]
        assert loc.startswith(redirect)
        assert "code=" in loc
        assert "state=st" in loc
        from urllib.parse import urlparse, parse_qs
        code = parse_qs(urlparse(loc).query)["code"][0]

        tok = await c.post(
            "/api/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect,
                "client_id": client_id,
                "code_verifier": verifier,
                "resource": "https://mcp.example.test/mcp",
            },
        )
        assert tok.status_code == 200
        assert tok.json()["access_token"] == "pk_test_spark"
        assert tok.json()["token_type"].lower() == "bearer"


@pytest.mark.asyncio
async def test_head_root_challenge(oauth_client):
    transport = ASGITransport(app=oauth_client)
    async with AsyncClient(transport=transport, base_url="https://mcp.example.test") as c:
        r = await c.head("/")
    assert r.status_code == 401
    www = r.headers.get("www-authenticate", "")
    assert "resource_metadata=" in www
    assert "oauth-protected-resource" in www
