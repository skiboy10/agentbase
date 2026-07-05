"""
Agentbase - FastAPI Application
"""
import asyncio
import secrets
from pathlib import Path
from contextlib import asynccontextmanager, AsyncExitStack

# Single source of truth for version — read from /app/VERSION (Docker) or repo root
_version_candidates = [Path("/app/VERSION"), Path(__file__).resolve().parents[2] / "VERSION"]
__version__ = next((f.read_text().strip() for f in _version_candidates if f.exists()), "0.0.0-dev")
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from app.middleware.proxy_secret import SecretGatedProxyHeadersMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import structlog

from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import init_db, async_session_maker
from app.core.encryption import decrypt_if_encrypted
from app.api import projects, providers, sources, prompts, agents, config, events, docs, jobs, metadata, auth, experiments
from app.api import taxonomy as taxonomy_api
from app.api import library
from app.api import evaluation
from app.models import ProviderConfig
from app.providers.registry import get_registry
from app.mcp import mcp, get_mcp_lifespan
from app.middleware.auth import BearerTokenMiddleware
from app.services.ingestion.watcher import watcher_manager

settings = get_settings()

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()

# Maximum JSON body size for non-file endpoints (1 MB).
# File uploads are already gated by max_upload_size_mb in the upload endpoint;
# this guard targets unbounded JSON payloads that could exhaust backend memory.
_MAX_JSON_BODY_BYTES = 1 * 1024 * 1024  # 1 MB


class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject JSON/form requests whose Content-Length exceeds the configured cap.

    File-upload endpoints are excluded — they buffer reads themselves and enforce
    per-file limits via max_upload_size_mb.
    """

    _UPLOAD_PATHS = {"/api/sources/upload", "/api/sources"}

    async def dispatch(self, request: Request, call_next):
        content_type = request.headers.get("content-type", "")
        is_upload = any(request.url.path.startswith(p) for p in self._UPLOAD_PATHS) and \
            "multipart/form-data" in content_type

        if not is_upload:
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > _MAX_JSON_BODY_BYTES:
                return Response(
                    content='{"detail": "Request body too large"}',
                    status_code=413,
                    media_type="application/json",
                )
        return await call_next(request)


def _run_alembic_migrations():
    """Run Alembic upgrade head (synchronous, called from thread pool).

    Tolerates the "database is ahead of the checked-out code" case: after
    switching to a branch whose migrations are behind what the shared dev
    database has already applied, Alembic can't resolve the DB's current
    revision against the local script tree and raises CommandError. Running
    against a DB that is *ahead* of the code is safe (extra tables/columns the
    code simply ignores), so we log loudly and continue instead of crashing
    app startup — a single branch switch must not take the service (and its
    MCP surface) down. Any other migration failure still propagates.
    """
    from alembic.config import Config
    from alembic import command
    from alembic.util.exc import CommandError
    from alembic.script.revision import ResolutionError

    alembic_cfg = Config("alembic.ini")
    try:
        command.upgrade(alembic_cfg, "head")
    except CommandError as exc:
        unresolved_revision = isinstance(exc.__cause__, ResolutionError) or (
            "Can't locate revision" in str(exc) or "No such revision" in str(exc)
        )
        if not unresolved_revision:
            raise
        logger.warning(
            "Skipping Alembic upgrade: database is ahead of the checked-out code "
            "(its current revision is not in the local migration tree). Safe to run "
            "against, but reconcile by switching to a branch that contains the "
            "migration or running 'alembic stamp'.",
            error=str(exc),
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    logger.info("Starting Agentbase", version=__version__)

    # Validate SECRET_KEY
    _insecure_keys = {"changeme-in-production", "changeme-generate-a-real-secret-key"}
    if not settings.secret_key:
        # Generate ephemeral key — sessions won't survive restarts
        _ephemeral_key = secrets.token_urlsafe(32)
        # Store on module-level since BaseSettings may be frozen
        object.__setattr__(settings, "secret_key", _ephemeral_key)
        logger.warning("SECRET_KEY not set — using ephemeral key. API keys and encrypted credentials will not survive restarts. Set SECRET_KEY in .env for persistence.")
    elif settings.secret_key in _insecure_keys:
        if settings.external_hostname:
            logger.error(
                "CRITICAL: SECRET_KEY is a known default and EXTERNAL_HOSTNAME is set. "
                "API keys and encrypted credentials are at risk. "
                "Set a unique SECRET_KEY in .env before exposing this instance. "
                "Generate one with: openssl rand -hex 32"
            )
        else:
            logger.warning("SECRET_KEY is still a default value. Set a unique SECRET_KEY in .env.")

    # Run Alembic migrations (in thread pool — Alembic uses asyncio.run() internally)
    logger.info("Running database migrations...")
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _run_alembic_migrations)
    # Restore log level — Alembic's fileConfig sets root to WARN, silencing INFO
    import logging as _logging
    _logging.getLogger().setLevel(_logging.INFO)
    logger.info("Database migrations complete")

    # Seed default data
    await init_db()

    # Load provider configurations from database
    # This allows providers configured via UI to persist across restarts
    logger.info("Loading provider configurations from database...")
    try:
        async with async_session_maker() as session:
            stmt = select(ProviderConfig).where(ProviderConfig.is_active == True)
            result = await session.execute(stmt)
            db_configs = result.scalars().all()

            registry = get_registry()
            from app.providers.embedding_registry import get_embedding_registry
            embedding_registry = get_embedding_registry()

            for db_config in db_configs:
                if db_config.api_key_encrypted:
                    # Decrypt at rest -> plaintext for the runtime registries.
                    # decrypt_if_encrypted tolerates legacy plaintext rows.
                    api_key = decrypt_if_encrypted(db_config.api_key_encrypted)
                    # Configure LLM provider
                    registry.configure_provider(
                        db_config.provider_name,
                        api_key=api_key,
                        base_url=db_config.base_url,
                    )
                    # Also configure embedding provider if applicable
                    embedding_registry.configure_provider(
                        db_config.provider_name,
                        api_key=api_key,
                    )
                    logger.info(
                        "Loaded provider from database",
                        provider=db_config.provider_name,
                    )
    except Exception as e:
        logger.error("Failed to load provider configs from database", error=str(e))

    # Log configured providers
    configured = settings.providers_configured
    registry = get_registry()
    logger.info(
        "Provider status",
        ollama=configured["ollama"] or registry.get_provider("ollama") is not None,
        openai=configured["openai"] or registry.get_provider("openai") is not None,
        anthropic=configured["anthropic"] or registry.get_provider("anthropic") is not None,
        grok=configured["grok"] or registry.get_provider("grok") is not None,
        google=configured["google"] or registry.get_provider("google") is not None,
    )

    # Recover stale jobs from previous crash
    async with async_session_maker() as db:
        from app.services.job_service import JobService
        job_svc = JobService(db)
        recovered = await job_svc.recover_stale_jobs(timeout_minutes=30)
        if recovered:
            logger.info("Recovered stale jobs", count=recovered)

    # Reset zombie sources stuck in "indexing" from a previous crash/restart
    from app.models import Source
    from sqlalchemy import update
    async with async_session_maker() as db:
        result = await db.execute(
            update(Source)
            .where(Source.status == "indexing")
            .values(
                status="error",
                progress_message="Reset: server restarted during indexing",
            )
        )
        await db.commit()
        if result.rowcount:
            logger.info("Reset zombie indexing sources", count=result.rowcount)

    # Start job worker loop
    from app.services.job_worker import job_worker_loop
    from app.services.job_handlers import (
        handle_index_source, handle_incremental_index,
        handle_retry_failed, handle_selective_index,
        handle_re_enrich_source,
        handle_watcher_events_gc, handle_generate_questions,
        handle_run_scorecard,
    )
    worker_task = asyncio.create_task(job_worker_loop({
        "index_source": handle_index_source,
        "incremental_index": handle_incremental_index,
        "retry_failed": handle_retry_failed,
        "selective_index": handle_selective_index,
        "re_enrich_source": handle_re_enrich_source,
        "watcher_events_gc": handle_watcher_events_gc,
        "generate_questions": handle_generate_questions,
        "run_scorecard": handle_run_scorecard,
    }))

    # Start maintenance scheduler (periodically enqueues watcher-event GC).
    # Replaces the previous startup-only enqueue so a long-running backend keeps
    # pruning watcher_events instead of letting them grow to millions of rows.
    from app.services.maintenance_scheduler import maintenance_scheduler_loop
    maintenance_task = asyncio.create_task(maintenance_scheduler_loop())

    # Start refresh scheduler (checks for automatic-policy sources due for re-index)
    from app.services.refresh_scheduler import refresh_scheduler_loop
    refresh_task = asyncio.create_task(refresh_scheduler_loop())

    # Start directory source watchers
    logger.info("Starting directory source watchers...")
    supervisor_task = None
    try:
        await watcher_manager.start_all()
        logger.info("Directory watchers started")
        supervisor_task = asyncio.create_task(watcher_manager.supervise_forever())
    except Exception as e:
        logger.error("Failed to start directory watchers", error=str(e))

    # Start MCP server session manager
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(get_mcp_lifespan())
        yield

    worker_task.cancel()
    refresh_task.cancel()
    maintenance_task.cancel()

    # Stop supervisor before stopping watchers
    if supervisor_task is not None:
        supervisor_task.cancel()
        try:
            await supervisor_task
        except asyncio.CancelledError:
            pass

    # Stop directory source watchers on shutdown
    logger.info("Stopping directory source watchers...")
    try:
        await watcher_manager.stop_all()
    except Exception as e:
        logger.error("Error stopping directory watchers", error=str(e))

    logger.info("Shutting down Agentbase")


app = FastAPI(
    title=settings.app_name,
    description="Open source knowledge curation engine — index, search, and serve specialized knowledge via LLMs",
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug_mode else None,
    redoc_url="/redoc" if settings.debug_mode else None,
    openapi_url="/openapi.json" if settings.debug_mode else None,
)

# Rate limiting (per-IP, applied to specific endpoints via decorators)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


async def _custom_rate_limit_handler(request, exc):
    """Return 429 with Retry-After header and JSON body."""
    retry_after = getattr(exc, "retry_after", 60)
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded. Try again in {retry_after} seconds"},
        headers={"Retry-After": str(retry_after)},
    )


app.add_exception_handler(RateLimitExceeded, _custom_rate_limit_handler)

# Proxy headers middleware (#49): rewrites scope["client"] / scope["scheme"]
# from X-Forwarded-For / X-Forwarded-Proto ONLY when an X-Internal-Forward-Secret
# header matches the shared secret nginx injects. Replaces uvicorn's
# ProxyHeadersMiddleware(trusted_hosts="*"), which trusted XFF from any client
# and let an attacker spoof their source IP as 127.0.0.1.
# Must be added before CORS middleware so the rewritten scheme is correct
# when CORS processes the request.
app.add_middleware(
    SecretGatedProxyHeadersMiddleware,
    secret=settings.internal_forward_secret,
)

# CORS middleware for frontend
# Configurable via ALLOWED_ORIGINS env var (comma-separated).
#
# IMPORTANT: "allow_credentials=True" and allow_origins=["*"] is invalid per the CORS
# spec — browsers will reject preflight responses with that combination. Always set
# explicit origins via ALLOWED_ORIGINS in .env (e.g. http://192.168.1.100:3002).
_DEV_ORIGINS = ["http://localhost:3002", "http://localhost:3000"]
cors_origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
if "*" in cors_origins:
    logger.critical(
        "CORS misconfiguration: allow_credentials=True cannot be combined with "
        "allow_origins=['*'] — browsers reject this combination. "
        "Falling back to dev-only origins. "
        "Set ALLOWED_ORIGINS in .env to your actual frontend URL."
    )
    cors_origins = _DEV_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Bearer token authentication (no-op when AUTH_TOKEN is not set)
app.add_middleware(BearerTokenMiddleware)


class _MCPSlashNormalizer:
    """Serve the MCP endpoint at both /mcp and /mcp/ without an HTTP redirect.

    Starlette's Mount 307-redirects /mcp -> /mcp/ to add the trailing slash.
    Behind the Tailscale Funnel (which terminates TLS and forwards plain HTTP
    to the backend) the redirect's Location is built with an http:// scheme,
    so MCP clients refuse to follow the https->http downgrade and report
    "failed to connect". Some remote-connector UIs also strip a trailing slash
    from the configured URL, so clients can't avoid hitting bare /mcp.
    Rewriting the path in-process serves /mcp directly and skips the redirect,
    so the connector URL works with or without the trailing slash.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") == "/mcp":
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


app.add_middleware(_MCPSlashNormalizer)

# Request body size cap for JSON endpoints (file uploads excluded — they self-limit).
app.add_middleware(RequestBodySizeLimitMiddleware)

# Include routers
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(providers.router, prefix="/api/providers", tags=["Providers"])
app.include_router(sources.router, prefix="/api/sources", tags=["Sources"])
app.include_router(prompts.router, prefix="/api/prompts", tags=["Prompts"])
app.include_router(agents.router, prefix="/api", tags=["Agents"])
app.include_router(config.router, prefix="/api/config", tags=["Config"])
app.include_router(events.router, prefix="/api", tags=["Events"])
app.include_router(docs.router, prefix="/api/docs", tags=["Documentation"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["Jobs"])
app.include_router(metadata.router, prefix="/api/metadata", tags=["Metadata"])
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(taxonomy_api.router, prefix="/api/taxonomies", tags=["Taxonomy"])
app.include_router(library.router, prefix="/api", tags=["Libraries"])
app.include_router(evaluation.router, prefix="/api/evaluation", tags=["Evaluation"])
app.include_router(experiments.router, prefix="/api/experiments", tags=["Experiments"])

# Mount MCP server for external agent access
# Wrap with auth context middleware — BaseHTTPMiddleware doesn't intercept
# mounted sub-apps, so MCP tools would see no auth context otherwise.
from app.core.auth import (
    set_current_auth, reset_current_auth, AUTH_TOKEN_SENTINEL, _is_external_request,
)


class _MCPAuthWrapper:
    """ASGI middleware that sets auth context for MCP requests.

    This wrapper is the connection-level gate check_mcp_scope() relies on:
    external requests must present a valid platform API key or they are
    rejected here with 401. (In AUTH_TOKEN mode BearerTokenMiddleware
    already rejects them earlier; this gate covers API-key-only mode,
    where that middleware passes unauthenticated requests through for
    REST require_scope() dependencies to decide — a mechanism MCP tools
    don't have.)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        ctx_token = None
        if scope["type"] == "http":
            req = Request(scope)
            headers = dict(req.headers)
            auth_header = headers.get("authorization", "")
            has_bearer = auth_header.startswith("Bearer ")
            token = auth_header[7:] if has_bearer else None

            settings = get_settings()
            if token is not None and settings.auth_token and \
                    secrets.compare_digest(token, settings.auth_token):
                # Global AUTH_TOKEN grants full access — honor it here too, or
                # external MCP clients authenticated via AUTH_TOKEN (already
                # admitted by BearerTokenMiddleware) would be rejected below.
                ctx_token = set_current_auth(AUTH_TOKEN_SENTINEL)
            elif token is not None:
                # Validate as a platform API key
                from app.services.auth_service import AuthService
                async with async_session_maker() as session:
                    try:
                        service = AuthService(session)
                        api_key = await service.validate_key(token)
                        if api_key:
                            ctx_token = set_current_auth(api_key)
                    except Exception as e:
                        logger.error("MCP token validation failed", error=str(e))

            if ctx_token is None:
                if not _is_external_request(req):
                    # Internal/LAN request gets full access if token was
                    # absent OR present-but-invalid (mirrors BearerTokenMiddleware)
                    ctx_token = set_current_auth(AUTH_TOKEN_SENTINEL)
                else:
                    # External without a valid key: reject at the connection
                    # level, mirroring require_scope() for REST routes.
                    logger.warning("Unauthenticated external MCP request rejected",
                                   path=req.url.path)
                    response = JSONResponse(
                        status_code=401,
                        content={"detail": "API key required"},
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                    await response(scope, receive, send)
                    return

        try:
            await self.app(scope, receive, send)
        finally:
            if ctx_token is not None:
                # Don't leak this request's auth into reused/spawned tasks
                reset_current_auth(ctx_token)


app.mount("/mcp", _MCPAuthWrapper(mcp.streamable_http_app()))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": __version__,
        "providers": settings.providers_configured,
    }


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": settings.app_name,
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }
