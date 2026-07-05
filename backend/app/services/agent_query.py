"""
Agent Query Service

Executes a user query against an agent's bound knowledge base and
returns a synthesized answer with source attribution.

This is a lightweight, stateless request/response pattern — no skills,
no streaming. Designed for the agent-as-a-service use case where callers
just need an authoritative answer grounded in the agent's knowledge.
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Agent, AgentLibrary, Source
from app.services.rag.service import RAGService
from app.services.rag.types import SearchResult
from app.services.provider_service import ProviderService
from app.providers.base import ChatMessage, MessageRole

logger = structlog.get_logger()


def _format_context(results: list[SearchResult]) -> str:
    """
    Format RAG results into a numbered context block for LLM injection.

    Each chunk is prefixed with a source reference so the LLM can cite
    sources in its answer.
    """
    parts = []
    for i, r in enumerate(results, 1):
        source_name = r.metadata.get("source_name", r.source or "Unknown")
        title = r.metadata.get("title", "")
        if title:
            header = f"[{i}] {title} (from {source_name})"
        else:
            header = f"[{i}] From {source_name}"
        parts.append(f"{header}\n{r.content}")
    return "\n\n".join(parts)


def _build_sources(results: list[SearchResult]) -> list[dict]:
    """
    Build the sources list for the response, deduplicated by (source_id, url).

    Returns one entry per unique source with preview and score of the
    highest-scoring chunk seen from that source.
    """
    seen: dict[tuple, dict] = {}
    for r in results:
        source_id = r.metadata.get("source_id", "")
        url = r.source or ""
        key = (source_id, url)
        if key not in seen or r.score > seen[key]["score"]:
            preview = r.content[:200] + "..." if len(r.content) > 200 else r.content
            seen[key] = {
                "source_id": source_id,
                "source_name": r.metadata.get("source_name", "Unknown"),
                "url": url,
                "title": r.metadata.get("title", ""),
                "score": r.score,
                "preview": preview,
            }
    return list(seen.values())


class AgentQueryService:
    """
    Executes a query against an agent's knowledge base.

    Flow:
    1. Load agent config (model, system prompt, knowledge bindings)
    2. Search bound knowledge sources via RAGService (hybrid multi-embedding)
    3. Build a numbered context block with source attribution
    4. Call the agent's LLM with system prompt + context + user query
    5. Return answer, sources, and model info
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def query(
        self,
        agent_id: str,
        query: str,
        filters: Optional[dict] = None,
        session_id: Optional[str] = None,
        include_raw_results: bool = False,
        overrides: Optional[dict] = None,
    ) -> dict:
        """
        Execute a query against an agent.

        Args:
            agent_id: UUID of the agent to query
            query: Natural language question
            filters: Optional metadata filters (passed through; reserved for
                     future Qdrant payload filtering support)
            session_id: Optional session ID (reserved; not used for stateless queries)
            include_raw_results: If True, add "raw_results" — the unmodified,
                                 rank-ordered list[SearchResult] from the search
                                 (used by evaluation scorecards for retrieval
                                 metrics; the default "sources" list is
                                 deduplicated and unsuitable for ranking math)
            overrides: Optional query-time config overrides for pipeline
                       experiments (evaluation slice 3). Keys are Agent column
                       names verbatim: system_prompt, model_provider,
                       model_name, temperature, rag_top_k. Applied on top of
                       the loaded agent's values for THIS query only — the
                       Agent row is never mutated. Unknown keys are ignored
                       (ExperimentService validates them at create time).

        Returns:
            dict with keys: answer, sources, query, model, agent_id
            (+ raw_results when include_raw_results=True)
        """
        # Load agent with both binding paths
        stmt = (
            select(Agent)
            .where(Agent.id == agent_id)
            .options(
                selectinload(Agent.source_bindings),
                selectinload(Agent.library_bindings),
            )
        )
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()

        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")

        # Resolve effective config once: overrides win, agent values otherwise.
        # Locals only — the Agent row must not be mutated by an experiment.
        overrides = overrides or {}
        eff = {field: overrides.get(field, getattr(agent, field))
               for field in ("system_prompt", "model_provider", "model_name",
                             "temperature", "rag_top_k")}

        # Collect source IDs from both binding paths:
        # 1. Legacy: AgentSource (per-source bindings)
        # 2. New: AgentLibrary → resolve to Source IDs via the Library's sources
        legacy_ids = [
            b.source_id for b in (agent.source_bindings or [])
        ]

        # For Library bindings, collect the source IDs from the Library
        # (via library_sources junction — a source may belong to multiple libraries)
        kb_source_ids: list[str] = []
        if agent.library_bindings:
            from app.models import LibrarySource
            kb_ids = [b.library_id for b in agent.library_bindings]
            kb_sources_stmt = (
                select(Source.id)
                .join(LibrarySource, LibrarySource.source_id == Source.id)
                .where(
                    LibrarySource.library_id.in_(kb_ids),
                    Source.status == "indexed",
                )
                .distinct()
            )
            kb_sources_result = await self.db.execute(kb_sources_stmt)
            kb_source_ids = [row[0] for row in kb_sources_result.all()]

        # Merge, deduplicate, KB sources first (priority)
        seen: set[str] = set()
        source_ids: list[str] = []
        for sid in kb_source_ids + legacy_ids:
            if sid not in seen:
                seen.add(sid)
                source_ids.append(sid)

        # Search knowledge base
        rag_results: list[SearchResult] = []
        if agent.use_rag and source_ids:
            rag_service = RAGService(self.db)
            try:
                rag_results = await rag_service.search_multi_embedding(
                    query=query,
                    source_ids=source_ids,
                    top_k=eff["rag_top_k"] or 5,
                )
            except Exception as e:
                logger.warning(
                    "RAG search failed, proceeding without context",
                    agent_id=agent_id,
                    error=str(e),
                )

        # Build LLM messages
        system_prompt = eff["system_prompt"] or ""

        if rag_results:
            context_block = _format_context(rag_results)
            system_prompt = (
                f"{system_prompt}\n\n"
                "## Relevant Documentation\n\n"
                "The following excerpts from the knowledge base may help answer "
                "the user's question:\n\n"
                f"{context_block}\n\n"
                "---\n\n"
                "Use the documentation above to provide an accurate, sourced answer. "
                "If the documentation does not cover the question, you may use your "
                "general knowledge but indicate when you are doing so."
            )

        messages = [ChatMessage(role=MessageRole.USER, content=query)]

        # Call LLM via provider gateway
        provider_service = ProviderService(self.db)
        provider = provider_service.get_provider(eff["model_provider"])
        if not provider:
            raise ValueError(f"Provider not configured: {eff['model_provider']}")

        chat_response = await provider.chat(
            messages=messages,
            model=eff["model_name"],
            temperature=eff["temperature"],
            system_prompt=system_prompt,
        )

        response = {
            "answer": chat_response.content,
            "sources": _build_sources(rag_results),
            "query": query,
            "model": f"{eff['model_provider']}/{eff['model_name']}",
            "agent_id": agent_id,
        }
        if include_raw_results:
            response["raw_results"] = rag_results
        return response
