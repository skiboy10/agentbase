"""
Qdrant client singleton — re-export of the canonical factory.
"""
from app.core.qdrant import get_qdrant_client, reset_qdrant_client

__all__ = ["get_qdrant_client", "reset_qdrant_client"]
