"""
Tests for the _MCPAuthWrapper connection-level auth gate in app.main.

The wrapper guards the mounted /mcp sub-app (BaseHTTPMiddleware doesn't
intercept mounted ASGI apps):
- External request without a valid Bearer key  -> 401, inner app never runs
- Internal/LAN request                         -> passes, AUTH_TOKEN_SENTINEL context
- External request with a valid platform key  -> passes, APIKey auth context
- External request with an invalid key        -> 401
- Non-HTTP scopes (lifespan)                   -> passed through untouched

The wrapper is exercised directly with fabricated ASGI scopes and a stub
inner app; external-ness is controlled by patching app.main's imported
_is_external_request (same approach as test_proxy_secret_middleware.py
uses for isolating middleware behavior).
"""
import pytest

import app.main as app_main
from app.core.auth import (
    AUTH_TOKEN_SENTINEL,
    get_current_auth,
    set_current_auth,
)


# ============================================================
# Test doubles
# ============================================================

class _FakeAPIKey:
    """Stands in for an app.models.APIKey row."""
    id = "key_test"
    name = "test key"
    scopes = ["admin"]


FAKE_KEY = _FakeAPIKey()
VALID_TOKEN = "ab_valid_platform_key"


class _StubInnerApp:
    """Records whether the wrapped MCP app was reached and with what auth."""

    def __init__(self):
        self.called = False
        self.seen_auth = "unset"
        self.seen_scope = None

    async def __call__(self, scope, receive, send):
        self.called = True
        self.seen_scope = scope
        self.seen_auth = get_current_auth()
        if scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})


class _StubSessionCtx:
    async def __aenter__(self):
        return None

    async def __aexit__(self, *args):
        return False


class _StubAuthService:
    """Validates only VALID_TOKEN; everything else is rejected."""

    def __init__(self, session):
        pass

    async def validate_key(self, token):
        return FAKE_KEY if token == VALID_TOKEN else None


# ============================================================
# Helpers
# ============================================================

def _http_scope(headers: dict | None = None) -> dict:
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    return {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/mcp/",
        "raw_path": b"/mcp/",
        "query_string": b"",
        "scheme": "http",
        "headers": raw_headers,
        "client": ("203.0.113.9", 51234),
        "server": ("testserver", 80),
    }


async def _receive():
    return {"type": "http.request", "body": b"", "more_body": False}


class _SendCollector:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self):
        for m in self.messages:
            if m["type"] == "http.response.start":
                return m["status"]
        return None

    @property
    def headers(self) -> dict:
        for m in self.messages:
            if m["type"] == "http.response.start":
                return {k.decode().lower(): v.decode() for k, v in m.get("headers", [])}
        return {}


@pytest.fixture(autouse=True)
def _reset_auth_context():
    set_current_auth(None)
    yield
    set_current_auth(None)


@pytest.fixture
def stubbed_validation(monkeypatch):
    """Route the wrapper's key validation through the in-memory stub."""
    monkeypatch.setattr(app_main, "async_session_maker", lambda: _StubSessionCtx())
    monkeypatch.setattr("app.services.auth_service.AuthService", _StubAuthService)


def _make_wrapper():
    inner = _StubInnerApp()
    wrapper = app_main._MCPAuthWrapper(inner)
    return wrapper, inner


# ============================================================
# Tests
# ============================================================

@pytest.mark.asyncio
async def test_external_without_key_rejected_401(monkeypatch):
    """External request with no Authorization header must be blocked."""
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: True)
    wrapper, inner = _make_wrapper()
    send = _SendCollector()

    await wrapper(_http_scope(), _receive, send)

    assert send.status == 401
    assert send.headers.get("www-authenticate") == "Bearer"
    assert not inner.called, "inner MCP app must never run for rejected requests"


@pytest.mark.asyncio
async def test_external_with_invalid_key_rejected_401(monkeypatch, stubbed_validation):
    """External request with a bogus Bearer token must also be blocked."""
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: True)
    wrapper, inner = _make_wrapper()
    send = _SendCollector()

    await wrapper(
        _http_scope(headers={"Authorization": "Bearer not-a-real-key"}),
        _receive,
        send,
    )

    assert send.status == 401
    assert not inner.called


@pytest.mark.asyncio
async def test_internal_without_key_passes_with_sentinel(monkeypatch):
    """Internal/LAN request passes through and gets full-access sentinel."""
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: False)
    wrapper, inner = _make_wrapper()
    send = _SendCollector()

    await wrapper(_http_scope(), _receive, send)

    assert inner.called
    assert send.status == 200
    assert inner.seen_auth == AUTH_TOKEN_SENTINEL


@pytest.mark.asyncio
async def test_external_with_valid_key_passes_with_api_key(monkeypatch, stubbed_validation):
    """External request presenting a valid platform key reaches the MCP app."""
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: True)
    wrapper, inner = _make_wrapper()
    send = _SendCollector()

    await wrapper(
        _http_scope(headers={"Authorization": f"Bearer {VALID_TOKEN}"}),
        _receive,
        send,
    )

    assert inner.called
    assert send.status == 200
    assert inner.seen_auth is FAKE_KEY


@pytest.mark.asyncio
async def test_external_with_global_auth_token_passes(monkeypatch):
    """AUTH_TOKEN mode: the global token must be honored by the MCP gate too.

    BearerTokenMiddleware admits external requests bearing AUTH_TOKEN; the
    wrapper must not then reject them for not being a platform API key.
    """
    class _Settings:
        auth_token = "global-lockdown-token"

    monkeypatch.setattr(app_main, "get_settings", lambda: _Settings())
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: True)
    wrapper, inner = _make_wrapper()
    send = _SendCollector()

    await wrapper(
        _http_scope(headers={"Authorization": "Bearer global-lockdown-token"}),
        _receive,
        send,
    )

    assert inner.called
    assert send.status == 200
    assert inner.seen_auth == AUTH_TOKEN_SENTINEL


@pytest.mark.asyncio
async def test_auth_context_reset_after_request(monkeypatch, stubbed_validation):
    """The wrapper must not leak this request's auth into the caller context."""
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: True)
    wrapper, inner = _make_wrapper()
    send = _SendCollector()

    await wrapper(
        _http_scope(headers={"Authorization": f"Bearer {VALID_TOKEN}"}),
        _receive,
        send,
    )

    assert inner.seen_auth is FAKE_KEY, "auth visible during the request"
    assert get_current_auth() is None, "auth reset once the request finished"


@pytest.mark.asyncio
async def test_non_http_scope_passes_through(monkeypatch):
    """Lifespan/websocket scopes are not gated (no Request parsing)."""
    # Would blow up if the wrapper tried to inspect this as HTTP
    monkeypatch.setattr(
        app_main, "_is_external_request",
        lambda req: (_ for _ in ()).throw(AssertionError("should not be called")),
    )
    wrapper, inner = _make_wrapper()
    send = _SendCollector()

    await wrapper({"type": "lifespan"}, _receive, send)

    assert inner.called
    assert inner.seen_scope == {"type": "lifespan"}
