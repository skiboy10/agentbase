"""Rename knowledge_sources→sources, knowledge_bases→libraries, and related tables/columns.

Phase 3 of the Sources/Libraries rename (#55).
Tables, FK columns, unique constraints, and indexes renamed to match new terminology.
DB model classes: KnowledgeSource→Source, KnowledgeBase→Library, etc.

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-04-09
"""
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Rename tables ──────────────────────────────────────────────
    op.rename_table("knowledge_bases", "libraries")
    op.rename_table("knowledge_sources", "sources")
    op.rename_table("project_knowledge_sources", "project_sources")
    op.rename_table("agent_knowledge_sources", "agent_sources")
    op.rename_table("agent_knowledge_bases", "agent_libraries")
    op.rename_table("knowledge_metadata_schemas", "source_metadata_schemas")

    # ── 2. Rename FK columns ──────────────────────────────────────────
    # sources.knowledge_base_id → sources.library_id
    op.alter_column("sources", "knowledge_base_id", new_column_name="library_id")
    # agent_sources.knowledge_source_id → agent_sources.source_id
    op.alter_column("agent_sources", "knowledge_source_id", new_column_name="source_id")
    # agent_libraries.knowledge_base_id → agent_libraries.library_id
    op.alter_column("agent_libraries", "knowledge_base_id", new_column_name="library_id")
    # documents.knowledge_base_id → documents.library_id
    op.alter_column("documents", "knowledge_base_id", new_column_name="library_id")

    # ── 3. Rename constraints (PostgreSQL — use actual DB names) ────────
    # Unique constraints
    op.execute("ALTER TABLE project_sources RENAME CONSTRAINT uq_project_knowledge_source TO uq_project_source")
    op.execute("ALTER TABLE agent_sources RENAME CONSTRAINT uq_agent_knowledge_source TO uq_agent_source")
    op.execute("ALTER TABLE agent_libraries RENAME CONSTRAINT agent_knowledge_bases_agent_id_knowledge_base_id_key TO uq_agent_library")
    op.execute("ALTER TABLE documents RENAME CONSTRAINT documents_knowledge_base_id_document_id_key TO uq_document_library_doc_id")
    # FK constraints referencing renamed tables/columns
    op.execute("ALTER TABLE agent_libraries RENAME CONSTRAINT agent_knowledge_bases_agent_id_fkey TO agent_libraries_agent_id_fkey")
    op.execute("ALTER TABLE agent_libraries RENAME CONSTRAINT agent_knowledge_bases_knowledge_base_id_fkey TO agent_libraries_library_id_fkey")
    op.execute("ALTER TABLE agent_sources RENAME CONSTRAINT agent_knowledge_sources_agent_id_fkey TO agent_sources_agent_id_fkey")
    op.execute("ALTER TABLE agent_sources RENAME CONSTRAINT agent_knowledge_sources_knowledge_source_id_fkey TO agent_sources_source_id_fkey")
    op.execute("ALTER TABLE project_sources RENAME CONSTRAINT project_knowledge_sources_project_id_fkey TO project_sources_project_id_fkey")
    op.execute("ALTER TABLE project_sources RENAME CONSTRAINT project_knowledge_sources_source_id_fkey TO project_sources_source_id_fkey")
    op.execute("ALTER TABLE sources RENAME CONSTRAINT knowledge_sources_project_id_fkey TO sources_project_id_fkey")
    op.execute("ALTER TABLE sources RENAME CONSTRAINT knowledge_sources_knowledge_base_id_fkey TO sources_library_id_fkey")
    op.execute("ALTER TABLE sources RENAME CONSTRAINT knowledge_sources_enrichment_taxonomy_id_fkey TO sources_enrichment_taxonomy_id_fkey")
    op.execute("ALTER TABLE sources RENAME CONSTRAINT fk_knowledge_sources_metadata_schema TO fk_sources_metadata_schema")
    op.execute("ALTER TABLE documents RENAME CONSTRAINT documents_knowledge_base_id_fkey TO documents_library_id_fkey")

    # ── 4. Rename indexes ───────────────────────────────────────────────
    # PKs
    op.execute("ALTER INDEX knowledge_sources_pkey RENAME TO sources_pkey")
    op.execute("ALTER INDEX knowledge_bases_pkey RENAME TO libraries_pkey")
    op.execute("ALTER INDEX agent_knowledge_bases_pkey RENAME TO agent_libraries_pkey")
    op.execute("ALTER INDEX agent_knowledge_sources_pkey RENAME TO agent_sources_pkey")
    op.execute("ALTER INDEX project_knowledge_sources_pkey RENAME TO project_sources_pkey")
    op.execute("ALTER INDEX knowledge_metadata_schemas_pkey RENAME TO source_metadata_schemas_pkey")
    # Column indexes on sources (was knowledge_sources)
    op.execute("ALTER INDEX ix_knowledge_sources_project_id RENAME TO ix_sources_project_id")
    op.execute("ALTER INDEX ix_knowledge_sources_metadata_schema_id RENAME TO ix_sources_metadata_schema_id")
    op.execute("ALTER INDEX ix_knowledge_sources_enrichment_taxonomy_id RENAME TO ix_sources_enrichment_taxonomy_id")
    op.execute("ALTER INDEX IF EXISTS idx_knowledge_sources_custom_metadata RENAME TO idx_sources_custom_metadata")
    op.execute("ALTER INDEX IF EXISTS idx_knowledge_sources_metadata RENAME TO idx_sources_metadata")
    # Unique indexes
    op.execute("ALTER INDEX knowledge_bases_collection_name_key RENAME TO libraries_collection_name_key")
    op.execute("ALTER INDEX knowledge_metadata_schemas_name_key RENAME TO source_metadata_schemas_name_key")


def downgrade() -> None:
    # ── 4. Restore index names ────────────────────────────────────────
    op.execute("ALTER INDEX source_metadata_schemas_name_key RENAME TO knowledge_metadata_schemas_name_key")
    op.execute("ALTER INDEX libraries_collection_name_key RENAME TO knowledge_bases_collection_name_key")
    op.execute("ALTER INDEX IF EXISTS idx_sources_metadata RENAME TO idx_knowledge_sources_metadata")
    op.execute("ALTER INDEX IF EXISTS idx_sources_custom_metadata RENAME TO idx_knowledge_sources_custom_metadata")
    op.execute("ALTER INDEX ix_sources_enrichment_taxonomy_id RENAME TO ix_knowledge_sources_enrichment_taxonomy_id")
    op.execute("ALTER INDEX ix_sources_metadata_schema_id RENAME TO ix_knowledge_sources_metadata_schema_id")
    op.execute("ALTER INDEX ix_sources_project_id RENAME TO ix_knowledge_sources_project_id")
    op.execute("ALTER INDEX source_metadata_schemas_pkey RENAME TO knowledge_metadata_schemas_pkey")
    op.execute("ALTER INDEX project_sources_pkey RENAME TO project_knowledge_sources_pkey")
    op.execute("ALTER INDEX agent_sources_pkey RENAME TO agent_knowledge_sources_pkey")
    op.execute("ALTER INDEX agent_libraries_pkey RENAME TO agent_knowledge_bases_pkey")
    op.execute("ALTER INDEX libraries_pkey RENAME TO knowledge_bases_pkey")
    op.execute("ALTER INDEX sources_pkey RENAME TO knowledge_sources_pkey")

    # ── 3. Restore constraint names ───────────────────────────────────
    op.execute("ALTER TABLE documents RENAME CONSTRAINT documents_library_id_fkey TO documents_knowledge_base_id_fkey")
    op.execute("ALTER TABLE sources RENAME CONSTRAINT fk_sources_metadata_schema TO fk_knowledge_sources_metadata_schema")
    op.execute("ALTER TABLE sources RENAME CONSTRAINT sources_enrichment_taxonomy_id_fkey TO knowledge_sources_enrichment_taxonomy_id_fkey")
    op.execute("ALTER TABLE sources RENAME CONSTRAINT sources_library_id_fkey TO knowledge_sources_knowledge_base_id_fkey")
    op.execute("ALTER TABLE sources RENAME CONSTRAINT sources_project_id_fkey TO knowledge_sources_project_id_fkey")
    op.execute("ALTER TABLE project_sources RENAME CONSTRAINT project_sources_source_id_fkey TO project_knowledge_sources_source_id_fkey")
    op.execute("ALTER TABLE project_sources RENAME CONSTRAINT project_sources_project_id_fkey TO project_knowledge_sources_project_id_fkey")
    op.execute("ALTER TABLE agent_sources RENAME CONSTRAINT agent_sources_source_id_fkey TO agent_knowledge_sources_knowledge_source_id_fkey")
    op.execute("ALTER TABLE agent_sources RENAME CONSTRAINT agent_sources_agent_id_fkey TO agent_knowledge_sources_agent_id_fkey")
    op.execute("ALTER TABLE agent_libraries RENAME CONSTRAINT agent_libraries_library_id_fkey TO agent_knowledge_bases_knowledge_base_id_fkey")
    op.execute("ALTER TABLE agent_libraries RENAME CONSTRAINT agent_libraries_agent_id_fkey TO agent_knowledge_bases_agent_id_fkey")
    op.execute("ALTER TABLE documents RENAME CONSTRAINT uq_document_library_doc_id TO documents_knowledge_base_id_document_id_key")
    op.execute("ALTER TABLE agent_libraries RENAME CONSTRAINT uq_agent_library TO agent_knowledge_bases_agent_id_knowledge_base_id_key")
    op.execute("ALTER TABLE agent_sources RENAME CONSTRAINT uq_agent_source TO uq_agent_knowledge_source")
    op.execute("ALTER TABLE project_sources RENAME CONSTRAINT uq_project_source TO uq_project_knowledge_source")

    # ── 2. Restore FK column names ────────────────────────────────────
    op.alter_column("sources", "library_id", new_column_name="knowledge_base_id")
    op.alter_column("agent_sources", "source_id", new_column_name="knowledge_source_id")
    op.alter_column("agent_libraries", "library_id", new_column_name="knowledge_base_id")
    op.alter_column("documents", "library_id", new_column_name="knowledge_base_id")

    # ── 1. Restore table names ────────────────────────────────────────
    op.rename_table("source_metadata_schemas", "knowledge_metadata_schemas")
    op.rename_table("agent_libraries", "agent_knowledge_bases")
    op.rename_table("agent_sources", "agent_knowledge_sources")
    op.rename_table("project_sources", "project_knowledge_sources")
    op.rename_table("sources", "knowledge_sources")
    op.rename_table("libraries", "knowledge_bases")
