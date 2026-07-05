"""
Agent Service - Manages deployable AI agents.

This service provides:
- Agent CRUD operations
- Source binding management
- API key generation for external access
"""
import asyncio
import re
import secrets
import hashlib
from typing import Optional
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from dataclasses import dataclass
from sqlalchemy import ColumnElement, select, delete, and_
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.models import Agent, AgentLibrary, AgentSource, Source, Project
from app.providers.registry import get_registry

logger = structlog.get_logger()

# Argon2 hasher for agent API keys
_agent_ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)

# Number of leading plaintext-key characters stored in Agent.api_key_prefix
# for indexed lookup. Keys look like "as_<43 urlsafe chars>", so 12 chars
# ("as_" + 9 random) are selective while remaining a tiny, non-secret
# fraction of the full key.
API_KEY_PREFIX_LENGTH = 12


def _hash_agent_key(plain_key: str) -> str:
    """Hash a plain agent API key using Argon2id."""
    return _agent_ph.hash(plain_key)


def _verify_agent_key(stored_hash: str, plain_key: str) -> tuple[bool, bool]:
    """
    Verify a plain agent API key against its stored hash.

    Returns (is_valid, needs_rehash).
    - is_valid: True if the key matches.
    - needs_rehash: True if the hash used legacy SHA-256 and should be upgraded.
    """
    if stored_hash.startswith("$argon2"):
        try:
            _agent_ph.verify(stored_hash, plain_key)
            return True, _agent_ph.check_needs_rehash(stored_hash)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False, False
    else:
        # Legacy SHA-256 fallback
        legacy = hashlib.sha256(plain_key.encode()).hexdigest()
        if secrets.compare_digest(legacy, stored_hash):
            return True, True  # valid but needs upgrade
        return False, False


# Default RAG context template for agents
DEFAULT_RAG_CONTEXT_TEMPLATE = """## Relevant Documentation

The following documentation excerpts may help answer the user's question:

{context}

---

Use this documentation to provide accurate, sourced answers. If the documentation doesn't cover the question, you may use your general knowledge but indicate when you're doing so."""


def generate_agent_id(name: str) -> str:
    """
    Generate a URL-safe agent_id from the agent name.

    Converts a human-readable label into a URL-safe API name:
    - Converts to lowercase
    - Replaces spaces and underscores with hyphens
    - Removes special characters
    - Collapses multiple hyphens

    Examples:
        "Customer Support Analyzer" -> "customer-support-analyzer"
        "ACME Data Importer" -> "acme-data-importer"
        "Test Agent (v2)" -> "test-agent-v2"
    """
    # Convert to lowercase
    slug = name.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)
    # Remove any character that isn't alphanumeric or hyphen
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    # Collapse multiple hyphens
    slug = re.sub(r'-+', '-', slug)
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    return slug


@dataclass
class AgentInfo:
    """Agent information returned from service."""
    id: str
    agent_id: Optional[str]  # URL-safe identifier
    name: str
    description: Optional[str]
    system_prompt: str
    model_provider: str
    model_name: str
    temperature: float
    use_rag: bool
    rag_top_k: int
    skills: list
    is_public: bool
    has_api_key: bool
    knowledge_source_ids: list[str]
    knowledge_base_ids: list[str]  # KBs bound via AgentLibrary
    created_at: str
    updated_at: str


class AgentService:
    """
    Service for agent management.

    Handles:
    - Agent CRUD operations
    - Source bindings
    - API key management
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_agents(self) -> list[Agent]:
        """List all agents."""
        stmt = select(Agent).options(
            selectinload(Agent.source_bindings),
            selectinload(Agent.library_bindings),
        ).order_by(Agent.name)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get a specific agent by ID with relationships loaded."""
        stmt = select(Agent).where(Agent.id == agent_id).options(
            selectinload(Agent.source_bindings),
            selectinload(Agent.library_bindings),
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _generate_unique_agent_id(self, name: str) -> str:
        """
        Generate a unique agent_id from the name.

        If the base slug is taken, appends -2, -3, etc.
        """
        base_slug = generate_agent_id(name)
        candidate = base_slug
        counter = 1

        while True:
            # Check if this agent_id already exists
            stmt = select(Agent).where(Agent.agent_id == candidate)
            result = await self.db.execute(stmt)
            if not result.scalar_one_or_none():
                return candidate
            # Try next suffix
            counter += 1
            candidate = f"{base_slug}-{counter}"

    async def _validate_model_available(
        self,
        provider_name: str,
        model_name: str,
    ) -> None:
        """
        Preflight check that an agent's configured model is actually servable.

        Raises ValueError if the provider isn't configured, or if the
        provider's model list is retrievable and the model isn't in it
        (e.g. an Ollama model that was never pulled — see #176).

        If the model list can't be retrieved (provider temporarily
        unreachable), the save is ALLOWED with a warning: a down provider
        must not brick agent editing. The query-time error mapping is the
        safety net in that case.
        """
        registry = get_registry()
        provider = registry.get_provider(provider_name)
        if not provider or not provider.is_configured:
            raise ValueError(
                f"Provider '{provider_name}' is not configured. "
                "Configure it on the Providers page before assigning it to an agent."
            )

        try:
            models = await provider.list_models()
        except Exception as e:
            logger.warning(
                "Model preflight skipped — could not list provider models",
                provider=provider_name,
                model=model_name,
                error=str(e),
            )
            return

        if not models:
            # Some providers (e.g. Ollama) return [] when unreachable — treat
            # the same as a failed listing and allow the save.
            logger.warning(
                "Model preflight skipped — provider returned no models",
                provider=provider_name,
                model=model_name,
            )
            return

        available = [m.id for m in models]
        if model_name not in available:
            sample = ", ".join(available[:5])
            suffix = ", ..." if len(available) > 5 else ""
            raise ValueError(
                f"Model '{model_name}' is not available on provider "
                f"'{provider_name}'. Available models include: {sample}{suffix}"
            )

    async def create_agent(
        self,
        name: str,
        system_prompt: str,
        model_provider: str,
        model_name: str,
        description: Optional[str] = None,
        temperature: float = 0.7,
        use_rag: bool = True,
        rag_top_k: int = 5,
        skills: Optional[list] = None,
        is_public: bool = False,
        knowledge_source_ids: Optional[list[str]] = None,
    ) -> Agent:
        """
        Create a new agent.

        The agent_id is auto-generated from the name (similar to a URL slug).

        Raises ValueError if the configured model fails preflight validation
        (provider not configured, or model not in the provider's model list).
        """
        # Preflight: fail fast on a model the provider can't serve (#176)
        await self._validate_model_available(model_provider, model_name)

        # Generate unique agent_id from name
        agent_id = await self._generate_unique_agent_id(name)

        agent = Agent(
            agent_id=agent_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            model_provider=model_provider,
            model_name=model_name,
            temperature=temperature,
            use_rag=use_rag,
            rag_top_k=rag_top_k,
            skills=skills or [],
            is_public=is_public,
        )

        self.db.add(agent)
        await self.db.flush()  # Get the agent ID

        # Add knowledge source bindings
        if knowledge_source_ids:
            await self._set_knowledge_sources(agent.id, knowledge_source_ids)

        await self.db.commit()

        logger.info("Created agent", agent_id=agent.id, name=name)

        # Re-fetch with relationships loaded
        return await self.get_agent(agent.id)

    async def update_agent(
        self,
        agent_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        system_prompt: Optional[str] = None,
        model_provider: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        use_rag: Optional[bool] = None,
        rag_top_k: Optional[int] = None,
        skills: Optional[list] = None,
        is_public: Optional[bool] = None,
        knowledge_source_ids: Optional[list[str]] = None,
    ) -> Optional[Agent]:
        """Update an existing agent.

        Raises ValueError if the model fields are being changed and the new
        provider/model combination fails preflight validation.
        """
        agent = await self.get_agent(agent_id)
        if not agent:
            return None

        # Preflight the model only when the effective provider/model actually
        # changes — unrelated edits must not fail on a model issue (#176).
        if model_provider is not None or model_name is not None:
            effective_provider = model_provider if model_provider is not None else agent.model_provider
            effective_model = model_name if model_name is not None else agent.model_name
            if (effective_provider != agent.model_provider
                    or effective_model != agent.model_name):
                await self._validate_model_available(effective_provider, effective_model)

        if name is not None:
            agent.name = name
        if description is not None:
            agent.description = description
        if system_prompt is not None:
            agent.system_prompt = system_prompt
        if model_provider is not None:
            agent.model_provider = model_provider
        if model_name is not None:
            agent.model_name = model_name
        if temperature is not None:
            agent.temperature = temperature
        if use_rag is not None:
            agent.use_rag = use_rag
        if rag_top_k is not None:
            agent.rag_top_k = rag_top_k
        if skills is not None:
            agent.skills = skills
        if is_public is not None:
            agent.is_public = is_public
            if not is_public and agent.api_key_hash:
                agent.api_key_hash = None
                agent.api_key_prefix = None
                logger.info("Revoked API key (is_public toggled off)", agent_id=agent_id)

        # Update knowledge source bindings if provided
        if knowledge_source_ids is not None:
            await self._set_knowledge_sources(agent_id, knowledge_source_ids)

        await self.db.commit()
        await self.db.refresh(agent)

        logger.info("Updated agent", agent_id=agent_id)

        return agent

    async def delete_agent(self, agent_id: str) -> bool:
        """Delete an agent. Returns True if deleted, False if not found."""
        agent = await self.get_agent(agent_id)
        if not agent:
            return False

        await self.db.delete(agent)
        await self.db.commit()

        logger.info("Deleted agent", agent_id=agent_id)
        return True

    async def duplicate_agent(
        self,
        agent_id: str,
        new_name: str,
    ) -> Optional[Agent]:
        """Duplicate an existing agent."""
        source = await self.get_agent(agent_id)
        if not source:
            return None

        # Get knowledge source IDs from the source agent
        knowledge_source_ids = [
            binding.source_id
            for binding in source.source_bindings
        ]

        return await self.create_agent(
            name=new_name,
            description=source.description,
            system_prompt=source.system_prompt,
            model_provider=source.model_provider,
            model_name=source.model_name,
            temperature=source.temperature,
            use_rag=source.use_rag,
            rag_top_k=source.rag_top_k,
            skills=source.skills.copy() if source.skills else [],
            is_public=False,  # Duplicates are not public by default
            knowledge_source_ids=knowledge_source_ids,
        )

    async def _set_knowledge_sources(
        self,
        agent_id: str,
        knowledge_source_ids: list[str]
    ):
        """Set the knowledge sources for an agent (replace all existing)."""
        # Delete existing bindings
        delete_stmt = delete(AgentSource).where(
            AgentSource.agent_id == agent_id
        )
        await self.db.execute(delete_stmt)

        # Add new bindings
        for source_id in knowledge_source_ids:
            # Verify source exists
            source_stmt = select(Source).where(
                Source.id == source_id
            )
            source_result = await self.db.execute(source_stmt)
            if source_result.scalar_one_or_none():
                binding = AgentSource(
                    agent_id=agent_id,
                    source_id=source_id
                )
                self.db.add(binding)

    async def get_knowledge_source_ids(self, agent_id: str) -> list[str]:
        """Get list of knowledge source IDs bound to an agent."""
        stmt = select(AgentSource.source_id).where(
            AgentSource.agent_id == agent_id
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    # ============================================================
    # API Key Management
    # ============================================================

    def generate_api_key(self) -> tuple[str, str]:
        """
        Generate a new API key.

        Returns:
            Tuple of (plain_key, hashed_key)
            The plain_key should be shown to user once, hashed_key stored in DB.
            hashed_key is an Argon2id hash (starts with '$argon2id$').
        """
        plain_key = f"as_{secrets.token_urlsafe(32)}"
        hashed_key = _hash_agent_key(plain_key)
        return plain_key, hashed_key

    async def set_api_key(self, agent_id: str) -> Optional[str]:
        """
        Generate and set a new API key for an agent.

        Returns:
            The plain API key (only returned once)
        """
        agent = await self.get_agent(agent_id)
        if not agent:
            return None

        plain_key, hashed_key = self.generate_api_key()
        agent.api_key_hash = hashed_key
        agent.api_key_prefix = plain_key[:API_KEY_PREFIX_LENGTH]
        agent.is_public = True

        await self.db.commit()
        await self.db.refresh(agent)

        logger.info("Generated API key for agent", agent_id=agent_id)
        return plain_key

    async def revoke_api_key(self, agent_id: str) -> bool:
        """Revoke an agent's API key."""
        agent = await self.get_agent(agent_id)
        if not agent:
            return False

        agent.api_key_hash = None
        agent.api_key_prefix = None

        await self.db.commit()
        await self.db.refresh(agent)

        logger.info("Revoked API key for agent", agent_id=agent_id)
        return True

    async def _fetch_key_candidates(self, prefix_filter: ColumnElement[bool]) -> list[Agent]:
        """Fetch public agents with an API key set, filtered by prefix clause."""
        stmt = select(Agent).where(
            and_(
                Agent.api_key_hash.isnot(None),
                Agent.is_public == True,
                prefix_filter,
            )
        ).options(
            selectinload(Agent.source_bindings),
            selectinload(Agent.library_bindings),
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def validate_api_key(self, api_key: str) -> Optional[Agent]:
        """
        Validate an API key and return the associated agent.

        Candidates are narrowed via the indexed api_key_prefix column (first
        API_KEY_PREFIX_LENGTH chars of the plaintext key) so an invalid key
        costs at most ~1 Argon2 verification instead of one per agent. Keys
        issued before the prefix column existed have a NULL prefix; if the
        prefix lookup finds nothing, those legacy rows are scanned as a
        fallback and the prefix is backfilled on successful validation.

        Argon2 verification is CPU-bound, so it runs via asyncio.to_thread
        to avoid blocking the event loop.

        Supports both Argon2id hashes (new keys) and SHA-256 hashes (legacy keys).
        On a successful SHA-256 match the hash is transparently upgraded to Argon2.

        Returns:
            The Agent if key is valid and agent is public, None otherwise
        """
        # Cheap format gate before any DB work or hashing: agent keys have
        # always been "as_" + token_urlsafe(32) (~46 chars). Rejecting junk
        # here keeps the legacy NULL-prefix fallback below from being an
        # Argon2 amplification vector for arbitrary garbage input.
        if not api_key.startswith("as_") or len(api_key) < 40:
            return None

        prefix = api_key[:API_KEY_PREFIX_LENGTH]
        candidates = await self._fetch_key_candidates(Agent.api_key_prefix == prefix)

        if not candidates:
            # Legacy fallback: rows created before the prefix column have a
            # NULL prefix and cannot be found via the indexed lookup.
            candidates = await self._fetch_key_candidates(
                Agent.api_key_prefix.is_(None)
            )

        matched_agent = None
        needs_rehash = False
        for candidate in candidates:
            is_valid, upgrade = await asyncio.to_thread(
                _verify_agent_key, candidate.api_key_hash, api_key
            )
            if is_valid:
                matched_agent = candidate
                needs_rehash = upgrade
                break

        if matched_agent is None:
            return None

        dirty = False

        # Transparent upgrade from legacy SHA-256 to Argon2
        if needs_rehash:
            matched_agent.api_key_hash = await asyncio.to_thread(
                _hash_agent_key, api_key
            )
            logger.info(
                "Upgraded agent API key hash from SHA-256 to Argon2",
                agent_id=matched_agent.id,
            )
            dirty = True

        # Opportunistic prefix backfill for keys issued before the prefix column
        if matched_agent.api_key_prefix is None:
            matched_agent.api_key_prefix = prefix
            logger.info(
                "Backfilled API key prefix for agent",
                agent_id=matched_agent.id,
            )
            dirty = True

        if dirty:
            await self.db.commit()

        return matched_agent

    async def build_system_prompt(
        self,
        agent: Agent,
        rag_context: Optional[str] = None,
        project_id: Optional[str] = None
    ) -> str:
        """
        Build the final system prompt, optionally injecting RAG context and project instructions.

        Args:
            agent: The Agent object
            rag_context: Formatted RAG context to inject (if any)
            project_id: Optional project ID to fetch additional instructions from

        Returns:
            The complete system prompt string
        """
        base_prompt = agent.system_prompt

        if rag_context and agent.use_rag:
            context_section = DEFAULT_RAG_CONTEXT_TEMPLATE.format(context=rag_context)
            base_prompt = f"{base_prompt}\n\n{context_section}"

        # Inject project instructions if a project_id is provided
        if project_id:
            stmt = select(Project).where(Project.id == project_id)
            result = await self.db.execute(stmt)
            project = result.scalar_one_or_none()
            if project and project.instructions:
                base_prompt = f"{base_prompt}\n\n## Project Instructions\n\nThe following instructions are specific to this project and must be followed:\n\n{project.instructions}"

        return base_prompt

    def to_info(self, agent: Agent) -> AgentInfo:
        """Convert Agent model to AgentInfo dataclass."""
        knowledge_source_ids = [
            binding.source_id
            for binding in agent.source_bindings
        ] if agent.source_bindings else []

        knowledge_base_ids = [
            binding.library_id
            for binding in agent.library_bindings
        ] if agent.library_bindings else []

        return AgentInfo(
            id=agent.id,
            agent_id=agent.agent_id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            model_provider=agent.model_provider,
            model_name=agent.model_name,
            temperature=agent.temperature,
            use_rag=agent.use_rag,
            rag_top_k=agent.rag_top_k,
            skills=agent.skills or [],
            is_public=agent.is_public,
            has_api_key=agent.api_key_hash is not None,
            knowledge_source_ids=knowledge_source_ids,
            knowledge_base_ids=knowledge_base_ids,
            created_at=agent.created_at.isoformat(),
            updated_at=agent.updated_at.isoformat(),
        )

    # ============================================================
    # Knowledge Base (KB) Binding — new preferred binding path
    # ============================================================

    async def bind_knowledge_base(
        self, agent_id: str, kb_id: str
    ) -> Optional[AgentLibrary]:
        """
        Bind a Knowledge Base to an agent.

        Returns the new binding, or None if agent/KB not found or already bound.
        """
        from app.models import Library as KBModel

        agent = await self.get_agent(agent_id)
        if not agent:
            return None

        kb_stmt = select(KBModel).where(KBModel.id == kb_id)
        kb_result = await self.db.execute(kb_stmt)
        if not kb_result.scalar_one_or_none():
            return None

        existing_stmt = select(AgentLibrary).where(
            AgentLibrary.agent_id == agent_id,
            AgentLibrary.library_id == kb_id,
        )
        existing_result = await self.db.execute(existing_stmt)
        if existing_result.scalar_one_or_none():
            return None  # Already bound

        binding = AgentLibrary(
            agent_id=agent_id,
            library_id=kb_id,
        )
        self.db.add(binding)
        await self.db.commit()

        logger.info("Bound KB to agent", agent_id=agent_id, kb_id=kb_id)
        return binding

    async def unbind_knowledge_base(self, agent_id: str, kb_id: str) -> bool:
        """
        Remove a KB binding from an agent.

        Returns True if removed, False if not found.
        """
        stmt = select(AgentLibrary).where(
            AgentLibrary.agent_id == agent_id,
            AgentLibrary.library_id == kb_id,
        )
        result = await self.db.execute(stmt)
        binding = result.scalar_one_or_none()

        if not binding:
            return False

        await self.db.delete(binding)
        await self.db.commit()

        logger.info("Unbound KB from agent", agent_id=agent_id, kb_id=kb_id)
        return True

    async def get_agent_knowledge_bases(self, agent_id: str) -> list:
        """Return all KnowledgeBases bound to an agent via AgentLibrary."""
        from app.models import Library as KBModel

        stmt = (
            select(KBModel)
            .join(AgentLibrary, KBModel.id == AgentLibrary.library_id)
            .where(AgentLibrary.agent_id == agent_id)
            .order_by(KBModel.name)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
