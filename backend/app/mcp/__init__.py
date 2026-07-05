"""
Agentbase MCP Server

Exposes Agentbase capabilities via Model Context Protocol (MCP),
enabling external AI agents to programmatically manage agents, skills,
knowledge sources, and projects.
"""

from app.mcp.server import mcp, get_mcp_lifespan

__all__ = ["mcp", "get_mcp_lifespan"]
