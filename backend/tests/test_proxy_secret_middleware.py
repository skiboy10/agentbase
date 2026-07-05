"""
Tests for SecretGatedProxyHeadersMiddleware (#49).

Covers:
- XFF + XFP honored when X-Internal-Forward-Secret matches
- XFF + XFP ignored when secret header absent
- XFF + XFP ignored when secret header present but wrong
- No-op when middleware initialized with secret=None (dev mode)
- Constant-time compare safe against unequal-length presented secrets
"""

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware.proxy_secret import SecretGatedProxyHeadersMiddleware


def _build_app(secret):
    async def echo(request: Request):
        return JSONResponse({
            "client_host": request.client.host if request.client else None,
            "scheme": request.url.scheme,
        })

    app = Starlette(routes=[Route("/echo", echo)])
    app.add_middleware(SecretGatedProxyHeadersMiddleware, secret=secret)
    return app


def test_no_secret_configured_is_noop(caplog):
    """When INTERNAL_FORWARD_SECRET is unset, XFF is ignored entirely."""
    app = _build_app(secret=None)
    client = TestClient(app)
    resp = client.get(
        "/echo",
        headers={
            "X-Forwarded-For": "1.2.3.4",
            "X-Forwarded-Proto": "https",
            # Even with a "matching" secret value, no-secret mode never honors.
            "X-Internal-Forward-Secret": "anything",
        },
    )
    body = resp.json()
    # TestClient peer is testclient/127.0.0.1; key thing is XFF didn't take.
    assert body["client_host"] != "1.2.3.4"
    assert body["scheme"] == "http"  # not rewritten to https


def test_secret_match_honors_xff_and_xfp():
    app = _build_app(secret="topsecret")
    client = TestClient(app)
    resp = client.get(
        "/echo",
        headers={
            "X-Forwarded-For": "1.2.3.4",
            "X-Forwarded-Proto": "https",
            "X-Internal-Forward-Secret": "topsecret",
        },
    )
    body = resp.json()
    assert body["client_host"] == "1.2.3.4"
    assert body["scheme"] == "https"


def test_secret_missing_does_not_honor_xff():
    app = _build_app(secret="topsecret")
    client = TestClient(app)
    resp = client.get(
        "/echo",
        headers={
            "X-Forwarded-For": "1.2.3.4",
            "X-Forwarded-Proto": "https",
            # No X-Internal-Forward-Secret header
        },
    )
    body = resp.json()
    assert body["client_host"] != "1.2.3.4"
    assert body["scheme"] == "http"


def test_secret_wrong_does_not_honor_xff():
    """The #49 attack: spoofed XFF with wrong/missing secret must be ignored."""
    app = _build_app(secret="topsecret")
    client = TestClient(app)
    resp = client.get(
        "/echo",
        headers={
            "X-Forwarded-For": "127.0.0.1",  # the spoof
            "X-Forwarded-Proto": "https",
            "X-Internal-Forward-Secret": "guessed-wrong",
        },
    )
    body = resp.json()
    assert body["client_host"] != "127.0.0.1"
    assert body["scheme"] == "http"


def test_unequal_length_secret_does_not_crash():
    """compare_digest must tolerate any length without raising."""
    app = _build_app(secret="topsecret-64-chars-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    client = TestClient(app)
    resp = client.get(
        "/echo",
        headers={
            "X-Forwarded-For": "1.2.3.4",
            "X-Internal-Forward-Secret": "x",  # 1 char
        },
    )
    assert resp.status_code == 200
    assert resp.json()["client_host"] != "1.2.3.4"


def test_xff_chain_takes_leftmost():
    """nginx appends upstream IP to any pre-existing XFF chain."""
    app = _build_app(secret="topsecret")
    client = TestClient(app)
    resp = client.get(
        "/echo",
        headers={
            "X-Forwarded-For": "203.0.113.7, 172.18.0.1",
            "X-Internal-Forward-Secret": "topsecret",
        },
    )
    assert resp.json()["client_host"] == "203.0.113.7"
