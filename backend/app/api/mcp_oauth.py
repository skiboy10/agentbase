"""
MCP OAuth 2.1 for Gemini Spark (and any MCP client that does RFC 9728/8414/7591).

Spark's Connected Apps flow: HEAD probe → protected-resource metadata →
authorization-server metadata → dynamic client registration → browser consent
→ PKCE token exchange → Bearer calls to /mcp.

Consent asks for an Agentbase platform API key. The access token *is* that key,
so the existing MCP wrapper validates it with no extra token store.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
import time
from html import escape
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
import structlog

from app.core.database import async_session_maker
from app.services.auth_service import AuthService

logger = structlog.get_logger()

router = APIRouter(tags=["MCP OAuth"])

# In-memory DCR + auth-code store. Spark re-registers after a backend restart.
_clients: dict[str, dict] = {}
_codes: dict[str, dict] = {}
CODE_TTL_SEC = 600
TOKEN_TTL_SEC = 30 * 24 * 3600  # Spark does not silently recover from expiry


def public_origin_from_headers(headers: dict, fallback_scheme: str = "https", fallback_host: str = "") -> str:
    """Origin Spark should use — honor forwarded proto/host from an HTTPS proxy."""
    proto = headers.get("x-forwarded-proto") or fallback_scheme
    host = headers.get("x-forwarded-host") or headers.get("host") or fallback_host
    return f"{proto}://{host}".rstrip("/")


def public_origin(request: Request) -> str:
    return public_origin_from_headers(
        {k.lower(): v for k, v in request.headers.items()},
        fallback_scheme=request.url.scheme,
        fallback_host=request.url.netloc,
    )


def _www_authenticate(origin: str) -> str:
    return (
        f'Bearer realm="mcp", '
        f'resource_metadata="{origin}/.well-known/oauth-protected-resource"'
    )


def unauthorized(origin: str) -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={"detail": "Authorization required"},
        headers={
            "WWW-Authenticate": _www_authenticate(origin),
            "Cache-Control": "no-store",
        },
    )


def _b64url_sha256(value: str) -> str:
    digest = hashlib.sha256(value.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _purge_codes() -> None:
    now = time.time()
    expired = [k for k, v in _codes.items() if v["exp"] < now]
    for k in expired:
        _codes.pop(k, None)


class RegisterBody(BaseModel):
    redirect_uris: list[str] = Field(min_length=1)
    client_name: Optional[str] = None
    token_endpoint_auth_method: Optional[str] = None
    grant_types: Optional[list[str]] = None
    response_types: Optional[list[str]] = None


def _prm(origin: str) -> dict:
    return {
        "resource": f"{origin}/mcp",
        "authorization_servers": [origin],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp:tools"],
        "resource_documentation": f"{origin}/",
    }


def _asm(origin: str) -> dict:
    return {
        "issuer": origin,
        "authorization_endpoint": f"{origin}/oauth/authorize",
        "token_endpoint": f"{origin}/api/oauth/token",
        "registration_endpoint": f"{origin}/api/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["mcp:tools"],
        "client_id_metadata_document_supported": True,
    }


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
async def protected_resource_metadata(request: Request):
    return JSONResponse(_prm(public_origin(request)))


@router.get("/.well-known/oauth-authorization-server")
async def authorization_server_metadata(request: Request):
    return JSONResponse(_asm(public_origin(request)))


@router.post("/api/oauth/register", status_code=201)
async def register_client(body: RegisterBody):
    https_uris = [u for u in body.redirect_uris if u.startswith("https://")]
    if not https_uris:
        raise HTTPException(status_code=400, detail="redirect_uris must include https://")
    client_id = "mcp-client-" + secrets.token_urlsafe(24)
    _clients[client_id] = {
        "client_id": client_id,
        "client_name": body.client_name or "MCP client",
        "redirect_uris": https_uris,
        "issued_at": int(time.time()),
    }
    logger.info("MCP OAuth DCR", client_id=client_id, name=body.client_name, uris=len(https_uris))
    return {
        "client_id": client_id,
        "client_id_issued_at": _clients[client_id]["issued_at"],
        "redirect_uris": https_uris,
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "client_name": _clients[client_id]["client_name"],
    }


def _consent_html(client_name: str, error: str = "") -> str:
    err = f'<p class="err">{escape(error)}</p>' if error else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Connect Agentbase</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:28rem;margin:4rem auto;padding:0 1rem;color:#111}}
h1{{font-size:1.25rem}} input,button{{width:100%;box-sizing:border-box;padding:.6rem;margin:.4rem 0}}
.err{{color:#b00020}} .muted{{color:#555;font-size:.9rem}}
</style></head><body>
<h1>Connect Gemini to Agentbase</h1>
<p class="muted">{escape(client_name)} wants to use your Agentbase MCP tools
(search, libraries, indexing). Paste a platform API key with <strong>write</strong>
scope. Create one under Configure → API Keys.</p>
{err}
<form method="post">
<label>API key<br><input name="api_key" type="password" required autocomplete="off" placeholder="pk_…"></label>
<button type="submit" name="decision" value="allow">Allow</button>
<button type="submit" name="decision" value="deny">Deny</button>
</form>
</body></html>"""


@router.get("/oauth/authorize")
async def authorize_get(
    request: Request,
    response_type: str = "",
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "S256",
    resource: str = "",
    scope: str = "",
):
    client = _clients.get(client_id)
    if response_type != "code" or not client or redirect_uri not in client["redirect_uris"]:
        raise HTTPException(status_code=400, detail="Invalid authorization request")
    if code_challenge_method != "S256" or not code_challenge:
        raise HTTPException(status_code=400, detail="PKCE S256 required")
    return HTMLResponse(_consent_html(client["client_name"]))


@router.post("/oauth/authorize")
async def authorize_post(
    request: Request,
    api_key: str = Form(""),
    decision: str = Form("deny"),
    client_id: str = Query(""),
    redirect_uri: str = Query(""),
    state: str = Query(""),
    code_challenge: str = Query(""),
):
    client = _clients.get(client_id)
    if not client or redirect_uri not in client["redirect_uris"]:
        raise HTTPException(status_code=400, detail="Invalid authorization request")

    def _redirect(**params: str) -> RedirectResponse:
        sep = "&" if "?" in redirect_uri else "?"
        return RedirectResponse(redirect_uri + sep + urlencode(params), status_code=302)

    if decision != "allow":
        q = {"error": "access_denied"}
        if state:
            q["state"] = state
        return _redirect(**q)

    async with async_session_maker() as db:
        key = await AuthService(db).validate_key(api_key.strip())
    if key is None or not key.is_active:
        return HTMLResponse(_consent_html(client["client_name"], "Invalid or inactive API key."), status_code=400)

    _purge_codes()
    code = secrets.token_urlsafe(32)
    _codes[code] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "challenge": code_challenge,
        "api_key": api_key.strip(),
        "exp": time.time() + CODE_TTL_SEC,
    }
    logger.info("MCP OAuth code issued", client_id=client_id)
    q = {"code": code}
    if state:
        q["state"] = state
    return _redirect(**q)


@router.post("/api/oauth/token")
async def token(request: Request):
    form = await request.form()
    grant = form.get("grant_type")
    code = form.get("code")
    redirect_uri = form.get("redirect_uri")
    client_id = form.get("client_id")
    verifier = form.get("code_verifier")
    if grant != "authorization_code" or not code or not verifier:
        raise HTTPException(status_code=400, detail="invalid_grant")
    rec = _codes.pop(str(code), None)
    if rec is None or rec["exp"] < time.time():
        raise HTTPException(status_code=400, detail="invalid_grant")
    if rec["client_id"] != client_id or rec["redirect_uri"] != redirect_uri:
        raise HTTPException(status_code=400, detail="invalid_grant")
    if _b64url_sha256(str(verifier)) != rec["challenge"]:
        raise HTTPException(status_code=400, detail="invalid_grant")
    return {
        "access_token": rec["api_key"],
        "token_type": "bearer",
        "expires_in": TOKEN_TTL_SEC,
        "scope": "mcp:tools",
    }
