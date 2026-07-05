-- Migration 013: Add Knowledge Base entity and Document model
-- Adds KnowledgeBase, Document, and AgentKnowledgeBase tables.
-- Adds knowledge_base_id (nullable) to knowledge_sources for backward compat.

-- KnowledgeBase: owns a single Qdrant collection, aggregates multiple sources
CREATE TABLE IF NOT EXISTS knowledge_bases (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    project_id VARCHAR(36) REFERENCES projects(id) ON DELETE SET NULL,

    -- Qdrant collection (1:1 with this KB)
    collection_name VARCHAR(255) NOT NULL UNIQUE,

    -- Embedding config enforced on all sources
    embedding_provider VARCHAR(100) NOT NULL,
    embedding_model VARCHAR(100) NOT NULL,
    embedding_dimensions INTEGER,

    -- Enrichment config (taxonomy_id is a plain reference, no FK yet)
    taxonomy_id VARCHAR(36),
    enrichment_model VARCHAR(100),

    -- Denormalized stats
    source_count INTEGER DEFAULT 0,
    document_count INTEGER DEFAULT 0,
    chunk_count INTEGER DEFAULT 0,

    status VARCHAR(20) DEFAULT 'active',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Document: logical document record within a knowledge base
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(36) PRIMARY KEY,
    knowledge_base_id VARCHAR(36) NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    source_id VARCHAR(36) NOT NULL REFERENCES knowledge_sources(id) ON DELETE CASCADE,

    -- Stable content-based identifier
    document_id VARCHAR(200) NOT NULL,

    title VARCHAR(500),
    file_path TEXT,
    url TEXT,
    file_type VARCHAR(20),

    full_text TEXT,
    text_length INTEGER DEFAULT 0,
    content_hash VARCHAR(64),

    -- Classification / taxonomy enrichment
    classification JSONB,
    classification_taxonomy_version INTEGER,
    document_type VARCHAR(50),

    chunk_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, indexed, stale, error
    error_message TEXT,
    indexed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT uq_kb_document UNIQUE (knowledge_base_id, document_id)
);

-- AgentKnowledgeBase: junction between agents and knowledge bases
CREATE TABLE IF NOT EXISTS agent_knowledge_bases (
    id VARCHAR(36) PRIMARY KEY,
    agent_id VARCHAR(36) NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    knowledge_base_id VARCHAR(36) NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT uq_agent_kb UNIQUE (agent_id, knowledge_base_id)
);

-- Add knowledge_base_id to knowledge_sources (nullable, backward-compatible)
ALTER TABLE knowledge_sources
    ADD COLUMN IF NOT EXISTS knowledge_base_id VARCHAR(36) REFERENCES knowledge_bases(id) ON DELETE SET NULL;

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_knowledge_bases_project_id ON knowledge_bases(project_id);
CREATE INDEX IF NOT EXISTS idx_documents_knowledge_base_id ON documents(knowledge_base_id);
CREATE INDEX IF NOT EXISTS idx_documents_source_id ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_agent_knowledge_bases_agent_id ON agent_knowledge_bases(agent_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_knowledge_base_id ON knowledge_sources(knowledge_base_id);
