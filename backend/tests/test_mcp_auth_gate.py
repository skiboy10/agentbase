"""
Tests for the _MCPAuthWrapper connection-level auth gate in app.main,
check_mcp_scope() tool-level enforcement, and BearerTokenMiddleware
contextvar reset.

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

check_mcp_scope() is covered two ways:
- Unit tests for each auth-context state, including fail-closed when no
  auth context is present (contextvar didn't propagate).
- An end-to-end test that drives a real stateless Streamable HTTP
  transport so a READ-scoped key hitting a WRITE-gated tool yields
  "Insufficient scope" — proving the contextvar reached the tool task.
"""
import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

import app.main as app_main
from app.core.auth import (
    AUTH_TOKEN_SENTINEL,
    Scope,
    check_mcp_scope,
    get_current_auth,
    set_current_auth,
)
from app.middleware.auth import BearerTokenMiddleware
from app.models import APIKey


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
async def test_tunnel_style_request_rejected_end_to_end(monkeypatch):
    """Integration of the gate with the REAL _is_external_request: a request
    from a trusted bridge-gateway IP that carries X-Forwarded-For (i.e.
    tunnel-proxied) must be rejected without a key."""
    class _Settings:
        external_hostname = "tunnel.example.com"
        auth_token = None
        trusted_networks = "127.0.0.1/32,192.168.0.0/16,172.16.0.0/12"
        trust_proxy = False

    import app.core.auth as core_auth
    monkeypatch.setattr(core_auth, "get_settings", lambda: _Settings())
    monkeypatch.setattr(app_main, "get_settings", lambda: _Settings())
    wrapper, inner = _make_wrapper()
    send = _SendCollector()

    scope = _http_scope(headers={
        "Host": "tunnel.example.com",
        "X-Forwarded-For": "203.0.113.9",
    })
    scope["client"] = ("172.17.0.1", 51234)  # Docker bridge gateway: trusted
    await wrapper(scope, _receive, send)

    assert send.status == 401
    assert not inner.called

    # ...while a direct localhost client (same source IP, no forwarding
    # headers) still passes without a key.
    send2 = _SendCollector()
    scope2 = _http_scope(headers={"Host": "localhost:8002"})
    scope2["client"] = ("172.17.0.1", 51235)
    await wrapper(scope2, _receive, send2)
    assert send2.status == 200
    assert inner.called


@pytest.mark.asyncio
async def test_rejection_log_includes_client_ip(monkeypatch):
    """The 401 log line must carry the TCP peer IP and the forwarded chain.

    In production the peer is the Docker bridge gateway and the real client
    only appears in X-Forwarded-For, so both must be logged."""
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: True)
    captured = {}

    def _warning(msg, **kwargs):
        captured["msg"] = msg
        captured.update(kwargs)

    monkeypatch.setattr(app_main.logger, "warning", _warning)
    wrapper, inner = _make_wrapper()
    send = _SendCollector()

    scope = _http_scope(headers={"X-Forwarded-For": "203.0.113.9"})
    scope["client"] = ("172.17.0.1", 51234)  # bridge gateway peer
    await wrapper(scope, _receive, send)

    assert send.status == 401
    assert captured.get("client_ip") == "172.17.0.1"
    assert captured.get("forwarded_for") == "203.0.113.9"
    assert captured.get("path") == "/mcp/"


@pytest.mark.asyncio
async def test_external_websocket_without_key_rejected(monkeypatch):
    """WebSocket upgrades must not bypass the connection-level gate."""
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: True)
    wrapper, inner = _make_wrapper()
    sent = []

    async def _send(message):
        sent.append(message)

    ws_scope = _http_scope()
    ws_scope["type"] = "websocket"
    ws_scope["scheme"] = "ws"
    del ws_scope["method"]

    async def _ws_receive():
        return {"type": "websocket.connect"}

    await wrapper(ws_scope, _ws_receive, _send)

    assert not inner.called, "inner app must not see unauthenticated websockets"
    assert sent and sent[0]["type"] == "websocket.close"


@pytest.mark.asyncio
async def test_internal_websocket_passes(monkeypatch):
    """Internal websocket connections keep working (full-access sentinel)."""
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: False)
    wrapper, inner = _make_wrapper()

    ws_scope = _http_scope()
    ws_scope["type"] = "websocket"
    ws_scope["scheme"] = "ws"
    del ws_scope["method"]

    async def _ws_receive():
        return {"type": "websocket.connect"}

    async def _send(message):
        pass

    await wrapper(ws_scope, _ws_receive, _send)

    assert inner.called
    assert inner.seen_auth == AUTH_TOKEN_SENTINEL


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


# ============================================================
# check_mcp_scope() unit tests
# ============================================================

def test_check_mcp_scope_auth_token_allows_all():
    """AUTH_TOKEN sentinel grants every scope."""
    set_current_auth(AUTH_TOKEN_SENTINEL)
    check_mcp_scope(Scope.READ)
    check_mcp_scope(Scope.WRITE)
    check_mcp_scope(Scope.ADMIN)


def test_check_mcp_scope_read_key_denied_write():
    """A READ-scoped platform key must not pass a WRITE check."""
    set_current_auth(APIKey(name="read-key", scopes=["read"]))
    with pytest.raises(ValueError, match="Insufficient scope"):
        check_mcp_scope(Scope.WRITE)


def test_check_mcp_scope_read_key_allows_read():
    set_current_auth(APIKey(name="read-key", scopes=["read"]))
    check_mcp_scope(Scope.READ)


def test_check_mcp_scope_write_key_allows_write():
    set_current_auth(APIKey(name="write-key", scopes=["write"]))
    check_mcp_scope(Scope.WRITE)


def test_check_mcp_scope_admin_key_allows_all():
    set_current_auth(APIKey(name="admin-key", scopes=["admin"]))
    check_mcp_scope(Scope.READ)
    check_mcp_scope(Scope.WRITE)
    check_mcp_scope(Scope.ADMIN)


def test_check_mcp_scope_no_auth_context_fails_closed():
    """No auth context means the contextvar didn't propagate (or the tool
    was invoked outside an MCP request). Every request admitted by
    _MCPAuthWrapper gets an auth context, so this state is anomalous and
    must be denied — allowing it would let a READ-scoped key execute
    WRITE/ADMIN tools if propagation ever regresses."""
    set_current_auth(None)
    with pytest.raises(ValueError, match="[Nn]o auth context"):
        check_mcp_scope(Scope.WRITE)


# ============================================================
# End-to-end: contextvar propagation through the real transport
# ============================================================

# JSON-RPC tools/call for a WRITE-gated tool. The bogus question_id makes
# the call side-effect free: the scope check runs before any DB access.
_TOOLS_CALL_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "agentbase_update_question",
        "arguments": {
            "question_id": "propagation-probe-missing-id",
            "status": "active",
        },
    },
}

_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def _make_real_transport_wrapper():
    """Build _MCPAuthWrapper around a real stateless Streamable HTTP
    transport running the production FastMCP tool registry — the same
    manager configuration app/mcp/server.py uses (stateless + JSON)."""
    from mcp.server.streamable_http_manager import StreamableHTTPSessionManager

    from app.mcp import mcp as fastmcp_instance

    manager = StreamableHTTPSessionManager(
        app=fastmcp_instance._mcp_server,
        json_response=True,
        stateless=True,
    )

    async def inner(scope, receive, send):
        await manager.handle_request(scope, receive, send)

    return manager, app_main._MCPAuthWrapper(inner)


def _tool_error_text(payload: dict) -> str:
    """Extract the human-readable error from a tools/call JSON-RPC body."""
    if payload.get("error"):
        err = payload["error"]
        return str(err.get("message") or err)
    result = payload.get("result") or {}
    content = result.get("content") or []
    if content:
        return content[0].get("text") or ""
    return str(payload)


@pytest.mark.asyncio
async def test_scope_enforced_through_real_stateless_transport(monkeypatch):
    """The auth contextvar set by _MCPAuthWrapper must propagate into the
    async task where the MCP tool executes.

    A READ-scoped key calling a WRITE-gated tool must produce the
    'Insufficient scope' error — proving the APIKey object itself was
    visible inside the tool call. If propagation regressed, check_mcp_scope
    would see None and (fail-closed) raise the distinct 'no auth context'
    error instead, so this asserts on the exact message.
    """
    httpx = pytest.importorskip("httpx")

    read_key = APIKey(name="probe-read-key", scopes=["read"])

    class _ReadKeyAuthService:
        def __init__(self, session):
            pass

        async def validate_key(self, token):
            return read_key if token == VALID_TOKEN else None

    monkeypatch.setattr(app_main, "async_session_maker", lambda: _StubSessionCtx())
    monkeypatch.setattr("app.services.auth_service.AuthService", _ReadKeyAuthService)
    monkeypatch.setattr(app_main, "_is_external_request", lambda req: True)

    manager, wrapper = _make_real_transport_wrapper()

    async with manager.run():
        transport = httpx.ASGITransport(app=wrapper)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            resp = await client.post(
                "/",
                headers={**_MCP_HEADERS, "Authorization": f"Bearer {VALID_TOKEN}"},
                json=_TOOLS_CALL_BODY,
            )

    assert resp.status_code == 200
    payload = resp.json()
    text = _tool_error_text(payload)
    result = payload.get("result") or {}
    if "isError" in result:
        assert result["isError"] is True
    assert "Insufficient scope" in text, (
        f"Expected the scope check to see the READ key; got: {text!r}"
    )
    assert "no auth context" not in text.lower(), (
        "Contextvar did not propagate into the MCP tool-call task"
    )


# ============================================================
# BearerTokenMiddleware contextvar reset
# ============================================================

def _middleware_request(path: str = "/api/echo", headers: dict | None = None) -> Request:
    raw_headers = [
        (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_bearer_middleware_resets_auth_after_internal_request(monkeypatch):
    """API-key mode, internal/LAN, no token: sentinel during the request,
    reset afterwards so the worker task cannot leak auth."""
    seen = {}

    async def call_next(request):
        seen["during"] = get_current_auth()
        return JSONResponse({"ok": True})

    class _Settings:
        auth_token = None

    monkeypatch.setattr("app.middleware.auth.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.core.auth._is_external_request", lambda req: False)

    mw = BearerTokenMiddleware(app=None)
    await mw.dispatch(_middleware_request(), call_next)

    assert seen["during"] == AUTH_TOKEN_SENTINEL
    assert get_current_auth() is None


@pytest.mark.asyncio
async def test_bearer_middleware_resets_auth_on_handler_error(monkeypatch):
    """reset_current_auth must run even when call_next raises."""
    async def call_next(request):
        raise RuntimeError("handler boom")

    class _Settings:
        auth_token = None

    monkeypatch.setattr("app.middleware.auth.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.core.auth._is_external_request", lambda req: False)

    mw = BearerTokenMiddleware(app=None)
    with pytest.raises(RuntimeError, match="handler boom"):
        await mw.dispatch(_middleware_request(), call_next)

    assert get_current_auth() is None


@pytest.mark.asyncio
async def test_bearer_middleware_resets_api_key_auth(monkeypatch):
    """API-key mode with a valid platform key must reset after call_next."""
    seen = {}

    async def call_next(request):
        seen["during"] = get_current_auth()
        return JSONResponse({"ok": True})

    class _Settings:
        auth_token = None

    async def _validate(self, token):
        return FAKE_KEY if token == VALID_TOKEN else None

    monkeypatch.setattr("app.middleware.auth.get_settings", lambda: _Settings())
    monkeypatch.setattr(BearerTokenMiddleware, "_validate_api_key", _validate)

    mw = BearerTokenMiddleware(app=None)
    request = _middleware_request(
        headers={"Authorization": f"Bearer {VALID_TOKEN}"}
    )
    await mw.dispatch(request, call_next)

    assert seen["during"] is FAKE_KEY
    assert get_current_auth() is None


@pytest.mark.asyncio
async def test_bearer_middleware_resets_auth_token_sentinel(monkeypatch):
    """AUTH_TOKEN mode (internal bypass) must reset the sentinel after."""
    seen = {}

    async def call_next(request):
        seen["during"] = get_current_auth()
        return JSONResponse({"ok": True})

    class _Settings:
        auth_token = "global-lockdown-token"

    monkeypatch.setattr("app.middleware.auth.get_settings", lambda: _Settings())
    monkeypatch.setattr("app.core.auth._is_external_request", lambda req: False)

    mw = BearerTokenMiddleware(app=None)
    await mw.dispatch(_middleware_request(), call_next)

    assert seen["during"] == AUTH_TOKEN_SENTINEL
    assert get_current_auth() is None
