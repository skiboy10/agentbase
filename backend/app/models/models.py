"""
SQLAlchemy database models.
"""
import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Boolean, Integer, Float, DateTime, ForeignKey, JSON, Index, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class Project(Base):
    """Project for organizing agents and knowledge sources."""
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    knowledge_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    knowledge_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    sources: Mapped[list["Source"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    prompts: Mapped[list["Prompt"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    assigned_sources: Mapped[list["ProjectSource"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProviderConfig(Base):
    """Configuration for LLM providers."""
    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    provider_name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    api_key_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    disabled_models: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class Source(Base):
    """A source of documents for RAG."""
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    last_indexed: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    progress_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    collection_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    embedding_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    embedding_dimensions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    selected_urls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    selected_files: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    custom_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    metadata_schema_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("source_metadata_schemas.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    default_metadata: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Enrichment pipeline config (Phase 2 — ingestion enrichment)
    enrichment_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    enrichment_taxonomy_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("taxonomies.id", ondelete="SET NULL"),
        nullable=True, index=True
    )
    enrichment_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # YouTube source configuration (only applies to source_type="youtube").
    # source_path holds the channel URL; these control how much of the back
    # catalogue to ingest. Per-channel by design (#133).
    youtube_backfill_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="recent")  # "all" | "recent"
    youtube_recent_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=50)

    # Directory watcher configuration (only applies to source_type="directory")
    watch_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    watch_extensions: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    watch_max_file_size_mb: Mapped[int] = mapped_column(Integer, default=50)
    watch_debounce_seconds: Mapped[int] = mapped_column(Integer, default=60)
    watch_depth: Mapped[int] = mapped_column(Integer, default=10)
    watch_mode: Mapped[str] = mapped_column(String(20), default="auto")
    watch_poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)

    # Watcher runtime state (managed by supervisor loop)
    watch_status: Mapped[str] = mapped_column(String(20), nullable=False, default="stopped")
    watch_last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    watch_last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Sub-source model:
    #   parent_source_id IS NULL  → root source (owns chunks + watcher)
    #   parent_source_id IS NOT NULL → sub-source (view over parent's chunks
    #                                   filtered by path_prefix; no own chunks,
    #                                   no own watcher, collection_name=NULL)
    parent_source_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"),
        nullable=True, index=True
    )
    path_prefix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    path_excludes: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Freshness lifecycle (WS2 — knowledge acquisition)
    freshness_policy: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default="none")  # "none" | "automatic" | "manual"
    stale_after_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    refresh_interval_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    next_refresh_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    project: Mapped[Optional["Project"]] = relationship(back_populates="sources")
    # passive_deletes=True on every child relationship below: each child FK
    # declares ON DELETE CASCADE, so Postgres deletes children server-side on a
    # parent delete. Without it, SQLAlchemy eagerly loads the full child graph
    # into memory to delete row-by-row — which froze the backend when a directory
    # source had millions of watcher_events. Let the database do the cascade.
    library_bindings: Mapped[list["LibrarySource"]] = relationship(
        "LibrarySource", back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )
    libraries: Mapped[list["Library"]] = relationship(
        "Library",
        secondary="library_sources",
        back_populates="sources",
        viewonly=True,
    )
    indexing_logs: Mapped[list["IndexingLog"]] = relationship(back_populates="source", cascade="all, delete-orphan", passive_deletes=True)
    project_assignments: Mapped[list["ProjectSource"]] = relationship(back_populates="source", cascade="all, delete-orphan", passive_deletes=True)
    agent_bindings: Mapped[list["AgentSource"]] = relationship(back_populates="source", cascade="all, delete-orphan", passive_deletes=True)
    scraped_contents: Mapped[list["DocumentContent"]] = relationship(back_populates="source", cascade="all, delete-orphan", passive_deletes=True)
    watcher_events: Mapped[list["WatcherEvent"]] = relationship(back_populates="source", cascade="all, delete-orphan", passive_deletes=True)

    # Self-referential parent/children for the sub-source model
    parent_source: Mapped[Optional["Source"]] = relationship(
        "Source",
        remote_side=[id],
        back_populates="sub_sources",
        foreign_keys=[parent_source_id],
    )
    sub_sources: Mapped[list["Source"]] = relationship(
        "Source",
        back_populates="parent_source",
        foreign_keys=[parent_source_id],
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class WatcherEvent(Base):
    """Durable log of watcher lifecycle and file events for a directory source."""
    __tablename__ = "watcher_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now(), index=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    severity: Mapped[str] = mapped_column(String(8), nullable=False, default="info")
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source: Mapped["Source"] = relationship(back_populates="watcher_events")

    __table_args__ = (
        Index("ix_watcher_events_source_timestamp", "source_id", text("timestamp DESC")),
    )


class IndexingLog(Base):
    """Per-URL indexing status log."""
    __tablename__ = "indexing_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scrape_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embed_duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    source: Mapped["Source"] = relationship(back_populates="indexing_logs")

    __table_args__ = (UniqueConstraint('source_id', 'url', name='uq_indexing_log_source_url'),)


class DocumentContent(Base):
    """Raw document content for re-embedding without re-scraping.

    Stores scraped web content, uploaded files, and directory-sourced documents.
    Renamed from ScrapedContent to reflect its broader scope.
    """
    __tablename__ = "document_content"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    content_length: Mapped[int] = mapped_column(Integer, default=0)
    scraped_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # File/directory source fields
    file_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # pdf, pptx, docx, md
    document_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # presentation, standard
    classification: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)  # enrichment results
    classification_taxonomy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # for stale detection
    classification_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # "llm" or "keyword"
    taxonomy_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("taxonomies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    __table_args__ = (UniqueConstraint('source_id', 'url', name='uq_document_content_source_url'),)
    source: Mapped["Source"] = relationship(back_populates="scraped_contents")


class ModelAssignment(Base):
    """Global or project-level model assignments for task types."""
    __tablename__ = "model_assignments"
    __table_args__ = (
        # Prevents duplicate assignments for the same (task_type, project_id) when project_id is NOT NULL
        UniqueConstraint('task_type', 'project_id', name='uq_model_assignment_task_project'),
        # Prevents duplicate global assignments (project_id IS NULL) — PostgreSQL treats NULLs as distinct
        # in regular unique constraints, so a partial unique index is needed for the NULL case
        Index('ix_model_assignment_task_global', 'task_type', unique=True,
              postgresql_where=text("project_id IS NULL")),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True)
    task_type: Mapped[str] = mapped_column(String(20), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


class Prompt(Base):
    """System prompts for agent task types."""
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    rag_context_template: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    use_rag: Mapped[bool] = mapped_column(Boolean, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    project: Mapped[Optional["Project"]] = relationship(back_populates="prompts")


class ProjectSource(Base):
    """Junction table linking global sources to projects."""
    __tablename__ = "project_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (UniqueConstraint('project_id', 'source_id', name='uq_project_source'),)
    project: Mapped["Project"] = relationship(back_populates="assigned_sources")
    source: Mapped["Source"] = relationship(back_populates="project_assignments")


class Agent(Base):
    """Deployable AI agent combining prompt, knowledge, and skills."""
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model_provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    temperature: Mapped[float] = mapped_column(Float, default=0.7)
    use_rag: Mapped[bool] = mapped_column(Boolean, default=True)
    rag_top_k: Mapped[int] = mapped_column(Integer, default=5)
    skills: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)
    api_key_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # First characters of the plaintext API key (e.g. "as_XXXXXXXXX"). Indexed
    # so key validation narrows to ~1 candidate before any Argon2 hashing.
    # Nullable: keys issued before this column existed have no prefix until
    # it is backfilled on their next successful validation.
    api_key_prefix: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    source_bindings: Mapped[list["AgentSource"]] = relationship(back_populates="agent", cascade="all, delete-orphan")
    library_bindings: Mapped[list["AgentLibrary"]] = relationship(back_populates="agent", cascade="all, delete-orphan")


class AgentSource(Base):
    """Junction table linking agents to their sources."""
    __tablename__ = "agent_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (UniqueConstraint('agent_id', 'source_id', name='uq_agent_source'),)
    agent: Mapped["Agent"] = relationship(back_populates="source_bindings")
    source: Mapped["Source"] = relationship(back_populates="agent_bindings")


class AgentLibrary(Base):
    """
    Junction table binding agents to Libraries.

    Library-level bindings query the library's Qdrant collection directly, which is faster
    than the legacy per-source filtering approach via AgentSource.
    Both binding paths work in parallel; legacy bindings are kept for backward compat.
    """
    __tablename__ = "agent_libraries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    agent_id: Mapped[str] = mapped_column(String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False)
    library_id: Mapped[str] = mapped_column(String(36), ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (UniqueConstraint('agent_id', 'library_id', name='uq_agent_library'),)
    agent: Mapped["Agent"] = relationship(back_populates="library_bindings")
    library: Mapped["Library"] = relationship(back_populates="agent_bindings")


class Library(Base):
    """
    A curated Library — the primary entity agents bind to.

    A Library has its own Qdrant collection and aggregates one or more
    Sources. Agents query the library's collection directly rather than
    iterating over individual sources.
    """
    __tablename__ = "libraries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Qdrant collection backing this KB
    collection_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)

    # Embedding configuration — nullable until first source is added, which locks in the model
    embedding_provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    embedding_dimensions: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Optional taxonomy and enrichment linkage
    taxonomy_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("taxonomies.id", ondelete="SET NULL"), nullable=True
    )
    enrichment_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Lifecycle status: "active", "building", "error"
    status: Mapped[str] = mapped_column(String(20), default="active")

    # Aggregate stats (denormalised for fast reads)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    document_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    source_bindings: Mapped[list["LibrarySource"]] = relationship(
        "LibrarySource", back_populates="library", cascade="all, delete-orphan"
    )
    sources: Mapped[list["Source"]] = relationship(
        "Source",
        secondary="library_sources",
        back_populates="libraries",
        viewonly=True,
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="library", cascade="all, delete-orphan"
    )
    agent_bindings: Mapped[list["AgentLibrary"]] = relationship(
        "AgentLibrary", back_populates="library", cascade="all, delete-orphan"
    )


class LibrarySource(Base):
    """Junction table for many-to-many Library ↔ Source relationship.

    A source can belong to multiple libraries (Stage 1 cross-library sharing).
    All sources bound to a library must share the same embedding model as the
    library; the first source added locks in the library's embedding config.
    """
    __tablename__ = "library_sources"

    library_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("libraries.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)

    library: Mapped["Library"] = relationship("Library", back_populates="source_bindings")
    source: Mapped["Source"] = relationship("Source", back_populates="library_bindings")


class Document(Base):
    """
    Tracks a single document ingested into a Library.

    Each Document corresponds to one source file/URL. The actual vector chunks
    live in Qdrant; this record holds the relational metadata and raw text
    for re-embedding without re-scraping.
    """
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    library_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )

    # Human-readable identifier (URL, file path, or slug)
    document_id: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Raw content (stored for re-embedding)
    full_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    text_length: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Source metadata
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    document_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Classification (from enrichment pipeline)
    classification: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    classification_taxonomy_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Indexing state
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('library_id', 'document_id', name='uq_document_library_doc_id'),
    )

    # Relationships
    library: Mapped["Library"] = relationship(back_populates="documents")
    source: Mapped[Optional["Source"]] = relationship("Source", lazy="selectin")


class SourceMetadataSchema(Base):
    """Defines available metadata fields for a source domain."""
    __tablename__ = "source_metadata_schemas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fields: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class Job(Base):
    """Persistent job queue for background operations."""
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    job_type: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="queued")
    priority: Mapped[int] = mapped_column(Integer, default=0)

    # What the job does
    payload: Mapped[dict] = mapped_column(JSON, default=dict)

    # Execution tracking
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)

    # Relationships
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())


# ============================================================
# Evaluation Models
# ============================================================

class QuestionSet(Base):
    """Golden question set owned by a Library — the evaluation ground-truth asset."""
    __tablename__ = "question_sets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    library_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    library: Mapped["Library"] = relationship()
    questions: Mapped[list["Question"]] = relationship(
        back_populates="question_set", cascade="all, delete-orphan"
    )


class Question(Base):
    """One golden test case. Statuses: draft | active | archived | stale.

    Questions with EvalResults can only be archived, never deleted
    (FK ondelete=RESTRICT on eval_results.question_id; service converts
    delete -> archive)."""
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    question_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("question_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expected_document_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    origin: Mapped[str] = mapped_column(String(20), default="manual")  # generated | manual
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    question_set: Mapped["QuestionSet"] = relationship(back_populates="questions")
    results: Mapped[list["EvalResult"]] = relationship(back_populates="question")


class EvalRun(Base):
    """A scorecard: one question set run against a target (library/agent/experiment)."""
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # library | agent | experiment
    target_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)  # polymorphic, no DB FK
    target_label: Mapped[str] = mapped_column(String(255), nullable=False)  # denormalized snapshot
    question_set_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("question_sets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_type: Mapped[str] = mapped_column(String(20), default="retrieval")  # retrieval | answer
    config_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    metrics_summary: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    question_set: Mapped["QuestionSet"] = relationship()
    results: Mapped[list["EvalResult"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    """One question's grade within an EvalRun."""
    __tablename__ = "eval_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    eval_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    retrieved: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    retrieval_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    answer_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    judge_scores: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    judge_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    run: Mapped["EvalRun"] = relationship(back_populates="results")
    question: Mapped["Question"] = relationship(back_populates="results")


# ============================================================
# Experiments (evaluation design doc §2, §4)
# ============================================================

class Experiment(Base):
    """Library-centered experiment (design doc §2). Slice 3 implements
    experiment_type='pipeline' (query-time agent overrides, no reindex);
    'index' (shadow collection rebuild) lands in Slice 4."""
    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    library_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("agents.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    experiment_type: Mapped[str] = mapped_column(String(20), default="pipeline")  # pipeline | index
    overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    shadow_collection: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)  # index type only (Slice 4)
    status: Mapped[str] = mapped_column(String(20), default="ready", index=True)  # pending|indexing|ready|promoted|error (first three are Slice-4 index states)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    library: Mapped["Library"] = relationship()
    agent: Mapped[Optional["Agent"]] = relationship()


class APIKey(Base):
    """Platform API key for authenticated access."""
    __tablename__ = "api_keys"


# 

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    key_prefix: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    rate_limit_rpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())


class Taxonomy(Base):
    """A named classification framework, optionally scoped to a project.

    Global taxonomies (project_id=NULL) are shared across all projects.
    Project-scoped taxonomies apply only within that project.
    """
    __tablename__ = "taxonomies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    project_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())

    terms: Mapped[list["TaxonomyTerm"]] = relationship(back_populates="taxonomy", cascade="all, delete-orphan")
    suggestions: Mapped[list["TaxonomySuggestion"]] = relationship(back_populates="taxonomy", cascade="all, delete-orphan")


class TaxonomyTerm(Base):
    """A single term within a taxonomy facet.

    Facets group terms by dimension (e.g., "platform", "product", "offering").
    Terms may be hierarchical via parent_value and carry keywords for auto-classification.
    """
    __tablename__ = "taxonomy_terms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    taxonomy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("taxonomies.id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    facet: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # list of strings for auto-classification
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint('taxonomy_id', 'facet', 'value', name='uq_taxonomy_term_facet_value'),
    )

    taxonomy: Mapped["Taxonomy"] = relationship(back_populates="terms")


class TaxonomySuggestion(Base):
    """Captures LLM-suggested terms not in the taxonomy for review."""
    __tablename__ = "taxonomy_suggestions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    taxonomy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("taxonomies.id", ondelete="CASCADE"), nullable=False
    )
    facet: Mapped[str] = mapped_column(String(100), nullable=False)
    suggested_value: Mapped[str] = mapped_column(String(200), nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    sample_document_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    merged_into: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint('taxonomy_id', 'facet', 'suggested_value', name='uq_taxonomy_suggestion'),
    )

    taxonomy: Mapped["Taxonomy"] = relationship(back_populates="suggestions")


# Backward-compatible aliases (all classes defined above — safe to reference here)
ScrapedContent = DocumentContent
KnowledgeSource = Source
KnowledgeBase = Library
ProjectKnowledgeSource = ProjectSource
AgentKnowledgeSource = AgentSource
AgentKnowledgeBase = AgentLibrary
KnowledgeMetadataSchema = SourceMetadataSchema
