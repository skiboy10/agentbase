"""
Qdrant client singleton.

Provides a single shared Qdrant client instance across the application.
"""
from typing import Optional
from qdrant_client import QdrantClient

from app.core.config import get_settings

settings = get_settings()

# Qdrant client singleton
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """Get or create Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
        )
    return _qdrant_client
