"""
Agentbase MCP Server

FastMCP instance that exposes Agentbase capabilities as MCP tools.
Tools are organized into modules under app/mcp/tools/.
"""

import contextlib
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
import structlog

from app.core.config import get_settings

logger = structlog.get_logger()

# Build allowed hosts list for DNS rebinding protection
# Always allow localhost; add external hostnames from EXTERNAL_HOSTNAME and ALLOWED_ORIGINS
_allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
_settings = get_settings()
if _settings.external_hostname:
    _allowed_hosts.append(f"{_settings.external_hostname}:*")
    _allowed_hosts.append(_settings.external_hostname)
# Extract hostnames from ALLOWED_ORIGINS (e.g. "https://foo.ts.net" → "foo.ts.net")
if _settings.allowed_origins and _settings.allowed_origins != "*":
    from urllib.parse import urlparse
    for origin in _settings.allowed_origins.split(","):
        parsed = urlparse(origin.strip())
        if parsed.hostname and parsed.hostname not in ("localhost", "127.0.0.1", "[::1]"):
            _allowed_hosts.append(f"{parsed.hostname}:*")
            _allowed_hosts.append(parsed.hostname)

# Create the FastMCP server instance
# Using stateless_http=True for production deployments
# streamable_http_path="/" ensures endpoint is at /mcp, not /mcp/mcp
mcp = FastMCP(
    name="agentbase_mcp",
    stateless_http=True,
    json_response=True,
    streamable_http_path="/",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=_allowed_hosts,
    ),
)

# Import tools to register them with the server
# These imports trigger the @mcp.tool() decorators
from app.mcp.tools import sources, sources_upload, sources_docs, source_ops, libraries, taxonomy, projects, agents, auth, guide, discovery, evaluation  # noqa: E402, F401


@contextlib.asynccontextmanager
async def get_mcp_lifespan():
    """
    Context manager for MCP server lifecycle.

    Should be used in the FastAPI lifespan to properly initialize
    and shutdown the MCP session manager.
    """
    logger.info("Starting MCP server session manager")
    async with mcp.session_manager.run():
        logger.info("MCP server ready")
        yield
    logger.info("MCP server shutdown")
