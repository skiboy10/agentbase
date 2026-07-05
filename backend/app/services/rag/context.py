"""
Context formatting for RAG service.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from qdrant_client import QdrantClient

from .types import RAGContext, RAGSource, SearchResult
from .search import search_standard


async def get_context_for_query(
    db: AsyncSession,
    client: QdrantClient,
    query: str,
    project_id: Optional[str] = None,
    top_k: int = 5,
    source_ids: Optional[list[str]] = None,
) -> RAGContext:
    """
    Get formatted context for a query, ready for LLM injection.

    Args:
        db: Database session
        client: Qdrant client
        query: The user's query
        project_id: Optional project scope
        top_k: Number of results to retrieve (this governs how much context is returned)
        source_ids: Optional list of specific source IDs to search (for agent-bound sources)

    Returns:
        RAGContext with formatted text and source attribution
    """
    results = await search_standard(db, client, query, project_id, top_k, source_ids=source_ids)

    if not results:
        return RAGContext(
            text="",
            sources=[],
            source_details=[],
            result_count=0
        )

    # Format context with source attribution
    context_parts = []
    sources = set()
    source_details = []
    seen_urls = set()  # Dedupe source_details by URL

    for i, result in enumerate(results, 1):
        source_name = result.metadata.get("source_name", result.source)
        title = result.metadata.get("title", "")

        # Format this result
        if title:
            header = f"[{i}] {title} (from {source_name})"
        else:
            header = f"[{i}] From {source_name}"

        chunk = f"{header}\n{result.content}\n"

        context_parts.append(chunk)
        sources.add(result.source)

        # Add to source_details if not already seen
        if result.source not in seen_urls:
            seen_urls.add(result.source)
            source_details.append(RAGSource(
                url=result.source,
                title=title or source_name,
                source_name=source_name,
                preview=result.content[:200] + "..." if len(result.content) > 200 else result.content
            ))

    return RAGContext(
        text="\n".join(context_parts),
        sources=list(sources),
        source_details=source_details,
        result_count=len(context_parts)
    )
