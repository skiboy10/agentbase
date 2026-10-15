"""
Canonical Qdrant client factory.

All other modules should import ``get_qdrant_client`` from here (or via the
thin re-exports in ``app.services.rag.client`` /
``app.services.ingestion.qdrant_client``) so there is a single singleton (#34).
"""
from typing import Optional

from qdrant_client import QdrantClient

from app.core.config import get_settings

_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """Get or create the shared Qdrant client."""
    global _qdrant_client
    if _qdrant_client is None:
        settings = get_settings()
        _qdrant_client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key if settings.qdrant_api_key else None,
        )
    return _qdrant_client


def reset_qdrant_client() -> None:
    """Clear the singleton (tests / client reconfiguration)."""
    global _qdrant_client
    _qdrant_client = None
