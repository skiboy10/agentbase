"""
Library Chat Service

Stateless multi-turn chat against a Library's knowledge base.
Retrieves relevant chunks via RAGService, builds conversation context,
and calls the configured LLM provider to produce a grounded response.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Library, Source
from app.services.rag.service import RAGService
from app.services.rag.types import SearchResult
from app.services.provider_service import ProviderService
from app.providers.base import ChatMessage as LLMChatMessage, MessageRole

logger = structlog.get_logger()

DEFAULT_SYSTEM_PROMPT = (
    "You are a knowledgeable assistant with access to a curated knowledge library. "
    "Answer questions based on the documentation provided. "
    "When citing information, reference the source by number (e.g., [1], [2]). "
    "If the documentation does not contain enough information to answer confidently, "
    "say so clearly rather than speculating."
)


def _format_context(results: list[SearchResult]) -> str:
    parts = []
    for i, r in enumerate(results, 1):
        # Use top-level citation fields on SearchResult (preferred over metadata dict)
        source_name = r.source_name or r.metadata.get("source_name", r.source or "Unknown")
        title = r.title or r.metadata.get("title", "")
        if title:
            header = f"[{i}] {title} (from {source_name})"
        else:
            header = f"[{i}] From {source_name}"
        parts.append(f"{header}\n{r.content}")
    return "\n\n".join(parts)


def _build_sources(results: list[SearchResult]) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for r in results:
        source_id = r.metadata.get("source_id", "")
        url = r.document_path or r.source or ""
        key = (source_id, url)
        if key not in seen or r.score > seen[key]["score"]:
            preview = r.content[:200] + "..." if len(r.content) > 200 else r.content
            seen[key] = {
                "source_id": source_id,
                "source_name": r.source_name or r.metadata.get("source_name", "Unknown"),
                "url": url,
                "title": r.title or r.metadata.get("title", ""),
                "score": r.score,
                "preview": preview,
            }
    return list(seen.values())


class LibraryChatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def chat(
        self,
        library_id: str,
        message: str,
        history: list[dict],
        config: dict,
    ) -> dict:
        # Load library
        stmt = select(Library).where(Library.id == library_id)
        result = await self.db.execute(stmt)
        library = result.scalar_one_or_none()
        if not library:
            raise ValueError(f"Library not found: {library_id}")

        # Resolve indexed source IDs for this library (via junction)
        from app.models import LibrarySource
        sources_stmt = (
            select(Source.id)
            .join(LibrarySource, LibrarySource.source_id == Source.id)
            .where(
                LibrarySource.library_id == library_id,
                Source.status == "indexed",
            )
        )
        sources_result = await self.db.execute(sources_stmt)
        source_ids = [row[0] for row in sources_result.all()]

        # Retrieve relevant chunks
        rag_results: list[SearchResult] = []
        top_k = config.get("top_k", 5)
        search_mode = config.get("search_mode", "hybrid")
        rerank = config.get("rerank", False)

        vector_weight = config.get("vector_weight", 0.7)

        if source_ids:
            rag_service = RAGService(self.db)
            try:
                if search_mode == "deep":
                    deep_resp = await rag_service.deep_search(
                        query=message,
                        knowledge_base_id=library_id,
                        top_k=top_k,
                        rerank=rerank,
                    )
                    rag_results = deep_resp.results
                elif search_mode == "hybrid":
                    rag_results = await rag_service.search_hybrid(
                        query=message,
                        source_ids=source_ids,
                        top_k=top_k,
                        vector_weight=vector_weight,
                        rerank=rerank,
                    )
                else:  # "vector"
                    rag_results = await rag_service.search_multi_embedding(
                        query=message,
                        source_ids=source_ids,
                        top_k=top_k,
                    )
            except Exception as e:
                logger.warning(
                    "RAG search failed, proceeding without context",
                    library_id=library_id,
                    error=str(e),
                )

        # Build system prompt
        system_prompt = config.get("system_prompt") or DEFAULT_SYSTEM_PROMPT
        if rag_results:
            context_block = _format_context(rag_results)
            system_prompt = (
                f"{system_prompt}\n\n"
                "## Knowledge Library Context\n\n"
                "The following excerpts from the library may be relevant:\n\n"
                f"{context_block}\n\n"
                "---\n\n"
                "Base your answer on the documentation above. "
                "Cite sources by number when referencing specific information."
            )

        # Build message list: history + current message
        messages: list[LLMChatMessage] = []
        for h in history:
            role = MessageRole.USER if h["role"] == "user" else MessageRole.ASSISTANT
            messages.append(LLMChatMessage(role=role, content=h["content"]))
        messages.append(LLMChatMessage(role=MessageRole.USER, content=message))

        # Call LLM
        provider_name = config.get("provider", "")
        model_name = config.get("model", "")
        if not provider_name or not model_name:
            raise ValueError("provider and model are required in config")

        provider_service = ProviderService(self.db)
        provider = provider_service.get_provider(provider_name)
        if not provider:
            raise ValueError(f"Provider not found: {provider_name}")
        if not provider.is_configured:
            raise ValueError(f"Provider is not configured (missing API key or endpoint): {provider_name}")

        chat_response = await provider.chat(
            messages=messages,
            model=model_name,
            system_prompt=system_prompt,
        )

        return {
            "answer": chat_response.content,
            "sources": _build_sources(rag_results),
            "model": f"{provider_name}/{model_name}",
        }
