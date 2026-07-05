# Agentbase - Architecture & Design

Reference architecture, design principles, and technical specifications for Agentbase.

---

## Platform Overview

Agentbase is a **self-hosted knowledge curation engine**. It provides core microservices for source ingestion, RAG, and agent configuration, exposed via REST API and MCP for integration by external applications.

```
Agentbase (Core Platform)
├── Core Microservices
│   ├── Source Service - Ingestion, chunking, embedding, vector storage
│   ├── Agent Service - Agent CRUD, configuration, API key management
│   ├── Provider Gateway - Multi-LLM abstraction (Ollama, OpenAI, Anthropic, Grok, Google)
│   └── Experiment Service - Pipeline A/B testing (agent config overrides, compare vs. baseline, promote); shadow-index experiments planned
├── Management UI - Configuration and monitoring interface
│   ├── Source curation (sources, indexing, search testing, pipeline health)
│   ├── Agent configuration (prompts, models, source bindings)
│   ├── Provider management (credentials, model selection)
│   └── Experimentation (A/B compare agent configs against question sets, promote winners)
└── Integration Interfaces
    ├── REST API - Headless access for applications and automation
    └── MCP Server - AI agent access (Claude Code, etc.) — 84 tools
```

---

## Interface Options

Agentbase is designed for flexibility with multiple access patterns:

| Interface | Audience | Use Case |
|-----------|----------|----------|
| **React Management UI** | Developers, ML Engineers | Source curation, agent configuration, provider management |
| **REST API** | Developers, Applications | Headless integration, custom UIs, automation pipelines |
| **MCP Server** | AI Agents | Claude Code, other AI tools access library directly |

The **headless API** enables embedding Agentbase capabilities into any application without the management UI. All functionality exposed via REST endpoints can be consumed programmatically.

---

## Design Principles

1. **Componentization** - Clear service boundaries with defined interfaces
2. **Plug-and-play** - Swap implementations without changing consumers
3. **Agentic-friendly** - Small, focused modules for AI-assisted development
4. **Dual interface** - Human UI + programmatic/agentic API access
5. **Separation of Concerns** - Core platform vs. domain-specific configuration
6. **Experimentable** - Compare chunking, embedding, and retrieval strategies
7. **Portable** - Run locally, on VMs, or in Kubernetes
8. **Extensible** - Plugin architecture for custom loaders, embedders, retrievers

### File Size Guidelines

| Type | Target | Hard Limit |
|------|--------|------------|
| Backend Service | 300-500 | 800 lines |
| Backend Router | 200-400 | 600 lines |
| Frontend Page | 200-400 | 600 lines |
| Frontend Component | 100-200 | 400 lines |

**Splitting Pattern:**
1. Create directory with same name as original file
2. Add barrel export (`__init__.py` or `index.ts`) immediately for backward compatibility
3. Split into focused modules (`types.py`, `orchestrator.py`, `sub_feature.py`)
4. Add `README.md` or `.context` file stating module mission

---

## Service Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        API Gateway                               │
│         (Auth, SSRF Protection, Rate Limiting, Routing)          │
└─────────────────────┬───────────────────────────────────────────┘
                      │
        ┌─────────────┼─────────────┬─────────────┐
        ▼             ▼             ▼             ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ Agent Service│ │ RAG Service  │ │  Provider    │ │  Ingestion   │
│              │ │              │ │  Gateway     │ │  Service     │
│ - CRUD       │ │ - Embed      │ │              │ │              │
│ - API keys   │ │ - Hybrid     │ │ - OpenAI     │ │ - Directory  │
│ - Source     │ │   search     │ │ - Anthropic  │ │   indexer    │
│   bindings   │ │ - Cross-     │ │ - Ollama     │ │ - Tika       │
│              │ │   encoder    │ │ - Grok       │ │   extraction │
│              │ │   reranking  │ │ - Google     │ │ - Enrichment │
└──────────────┘ └──────────────┘ └──────────────┘ │ - Watchers   │
                                                    └──────────────┘
```

### Service Interfaces

| Service | Interface Methods | Responsibility |
|---------|-------------------|----------------|
| **RAGService** | `embed()`, `search()`, `search_hybrid()`, `search_grouped()`, `deep_search()`, `get_context_for_query()` | Vector search, hybrid search, deep search with query decomposition, cross-encoder reranking, context retrieval |
| **IngestionService** | `ingest_url()`, `ingest_directory()`, `get_status()` | Web scraping, document processing, directory indexing |
| **EnrichmentService** | `enrich()` | Text cleaning, document type detection, LLM classification |
| **RerankerService** | `rerank()` | Cross-encoder reranking via FlashRank (local) with Ollama fallback |
| **QueryDecomposer** | `decompose()` | LLM-based query decomposition via Ollama (gemma4:e4b) with rule-based fallback |
| **ProviderService** | `chat()`, `chat_stream()`, `get_model_for_task()` | LLM routing, provider abstraction |
| **PromptService** | `get_default_prompt()`, `build_system_prompt()` | Prompt management, template assembly |
| **AgentService** | `create()`, `update()`, `delete()`, `list()` | Agent CRUD, API key management, source bindings |
| **LibraryChatService** | `chat()` | Multi-turn RAG chat against a Library: retrieves chunks, builds context, calls LLM, returns answer + sources |

---

## Core Entity Relationships

Libraries and Agents are the primary organizing entities. Projects are deprecated (#56).

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PROJECT  (deprecated — #56)                     │
│  (was primary scope - organizing agents, sources, prompts, and models)      │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ├──────────────┬──────────────┬──────────────┐
         ▼              ▼              ▼              ▼
   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
   │  PROMPTS │  │ SOURCES  │  │  MODELS  │  │  AGENTS  │
   │          │  │          │  │(assigned)│  │          │
   └──────────┘  └────┬─────┘  └──────────┘  └────┬─────┘
                      │                            │
                      └────────────────────────────┘
                                    │
                              (Source bindings:
                               agents select which
                               sources to use for RAG)

   ┌──────────┐  ┌──────────────┐
   │ TAXONOMY │  │  LIBRARY     │
   │ + TERMS  │  │              │
   └────┬─────┘  └──────┬───────┘
        │               │
        │               ├── Sources (members)
        │               └── Documents (full text + classification)
        │
        └── EnrichmentConfig (per Source)
            (drives LLM classification during indexing)
```

### Entity Definitions

| Entity | Scope | Description |
|--------|-------|-------------|
| **Project** | Global | (Deprecated — #56) Container for organizing agents, sources, prompts, and models. Being replaced by Libraries. |
| **Prompt** | Project | System prompts with versioning. Defines agent behavior per task type. |
| **Source** | Global | URL, file, GitHub, or directory sources. Indexed into vector store. Assignable to agents. (DB model: `Source`) |
| **ScrapedContent** | Source | Raw scraped content stored for re-embedding experiments. |
| **ModelAssignment** | Project | Maps task types to provider/model pairs. |
| **Agent** | Global | Configured agent with model, prompt, API key, and source bindings. |
| **Experiment** | Library | Pipeline experiments (agent config overrides, compare-vs-baseline, promote); index experiments (shadow re-index) planned. |
| **Taxonomy** | Global | Hierarchical classification schema with terms and keywords. Drives LLM enrichment. |
| **TaxonomyTerm** | Taxonomy | Individual classification category with keyword fallback list. |
| **Library** | Global | Named collection grouping sources with a shared Qdrant collection and embedding config. (DB model: `Library`) |
| **Document** | Library | Full-text record of an indexed file, with classification metadata and content hash for change detection. |
| **QuestionSet** | Library | Golden evaluation questions for a library — generated from its documents, human-curated. |
| **Question** | QuestionSet | One test case: question text, expected answer criteria, expected document ids. Lifecycle: draft → active → archived/stale. |
| **EvalRun** | QuestionSet | A scorecard: one question-set run against a target (library / agent / experiment), with config snapshot and aggregate metrics. |
| **EvalResult** | EvalRun | Per-question grade: retrieved docs, retrieval metrics, judged answer scores. |

### Key Relationships
- Agents bind to Libraries via `AgentLibrary` (preferred) or to individual Sources via `AgentSource`
- Sources were assigned to Projects via `ProjectSource` junction table (deprecated — #56)
- RAG search filters by source_id to retrieve relevant content (hybrid search with RRF)
- ScrapedContent enables re-embedding without re-scraping
- Experiments are library-scoped: pipeline type overrides an agent's config at query time and is graded via EvalRuns; promote writes the winning overrides into the agent
- Sources optionally belong to a Library; library-aware indexing creates Document records
- Taxonomy drives LLM classification during directory indexing; keyword fallback when LLM unavailable
- Classification metadata is stored both in Postgres (Document.classification) and Qdrant chunk payloads
- Libraries own QuestionSets; EvalRuns reference targets polymorphically (target_type + target_id, with a denormalized label so history survives target deletion). Full evaluation design: docs/evaluation-experiments-design.md

---

## Dual Database Architecture

Separate content storage from vector storage to enable experimentation and content versioning.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         INGESTION PIPELINE                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    ▼                               ▼                               ▼
┌─────────┐                  ┌─────────────┐                 ┌─────────────┐
│  URLs   │                  │    PDFs     │                 │ Directories │
└────┬────┘                  └──────┬──────┘                 └──────┬──────┘
     │                              │          Tika extraction        │
     │                              │    (PDF, PPTX, DOCX, PPT)      │
     └──────────────────────────────┼───────────────────────────────┘
                                    ▼
                    ┌───────────────────────────────┐
                    │      ENRICHMENT PIPELINE       │
                    │  1. Text cleaning              │
                    │  2. Document type detection    │
                    │  3. LLM classification         │
                    │     (qwen3:14b via Ollama)     │
                    │  4. Taxonomy matching           │
                    │  5. Keyword fallback           │
                    └───────────────┬───────────────┘
                                    │
                         ┌─────────────────────┐
                         │   CONTENT DATABASE  │  ◄── PostgreSQL
                         │   (Raw Documents)   │
                         │                     │
                         │  • ScrapedContent   │
                         │  • Document         │
                         │    (full text +     │
                         │     classification) │
                         │  • SourceMetadata   │
                         └──────────┬──────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │ Chunker  │   │ Chunker  │   │ Chunker  │
              │ Config A │   │ Config B │   │ Config C │
              └────┬─────┘   └────┬─────┘   └────┬─────┘
                   │              │              │
                   ▼              ▼              ▼
              ┌──────────┐   ┌──────────┐   ┌──────────┐
              │ Embedder │   │ Embedder │   │ Embedder │
              │ Model A  │   │ Model B  │   │ Model C  │
              └────┬─────┘   └────┬─────┘   └────┬─────┘
                   │              │              │
                   └──────────────┼──────────────┘
                                  ▼
                       ┌─────────────────────┐
                       │   VECTOR DATABASE   │  ◄── Qdrant
                       │   (Embeddings)      │
                       │                     │
                       │  • agentbase_*      │
                       │    collections      │
                       │  • Text index for   │
                       │    hybrid search    │
                       │  • Classification   │
                       │    metadata in      │
                       │    chunk payloads   │
                       └─────────────────────┘
```

**Design Decision:** Raw content is stored once. Chunking and embedding configurations are defined per embedding run, allowing experimentation without duplicating content storage. Tika handles binary document extraction (PDF, PPTX, DOCX); plain text and Markdown are processed directly.

---

## Knowledge Pipeline v2 — Native Ingestion

n8n is retired. All source lifecycle operations are now native to Agentbase.

### Directory Indexer

The primary ingestion path for file-based sources. Handles `.md`, `.txt`, `.html`, `.json`, `.pdf`, `.pptx`, `.docx`.

- **Tika extraction** for binary documents (PDF, PPTX, DOCX) via Apache Tika HTTP API
- **Library-aware mode**: when a source belongs to a Library, creates `Document` records in Postgres and skips unchanged files via `content_hash` comparison
- **Enrichment pipeline** runs inline: text cleaning → document type detection → LLM classification
- **Classification payload** written to both the `Document` record and each Qdrant chunk's `metadata`

### File Watchers

Directory-type sources can be monitored for changes automatically:

| Mode | Mechanism | Use Case |
|------|-----------|----------|
| `events` | watchdog OS-level filesystem events | Local directories, low latency |
| `polling` | Periodic mtime scan | Network drives, containers where inotify is unavailable |
| `auto` | Starts in event mode, falls back to polling if no events seen within 2× poll interval | Default for new sources |

The watcher service runs on a background asyncio loop. Blocking I/O (file hashing, Qdrant calls) is dispatched to `ThreadPoolExecutor` to avoid blocking the event loop.

### Enrichment Pipeline

Runs during indexing for directory sources with enrichment enabled.

```
raw text
    ↓  text_cleaner  (artifact removal, whitespace normalization)
    ↓  document type detection  (presentation vs. standard)
    ↓  LLM classification  (qwen3:14b, temperature 0.1)
         └── taxonomy prompt: classify against TaxonomyTerms
         └── keyword fallback: term.keyword_list match when LLM unavailable
    ↓  classification payload  → Qdrant chunk metadata + Postgres Document
```

**Re-enrichment** (`services/ingestion/re_enrichment.py`): scrolls existing Qdrant chunks for a source and re-runs LLM classification without re-indexing. Triggered via API or MCP. Progress tracked on the `Source` record.

---

## Qdrant Payload Schema

Each chunk stored in Qdrant includes:

```json
{
  "content": "chunk text",
  "source": "https://url or /path/to/file",
  "source_id": "uuid",
  "chunk_index": 0,
  "title": "Page or File Title",
  "content_hash": "sha256...",
  "scraped_at": "2026-01-15T12:00:00",
  "embedding_model": "ollama/mxbai-embed-large",
  "document_id": "uuid (library-aware sources only)",
  "library_id": "uuid (library-aware sources only)",
  "metadata": {
    "file_type": "pdf",
    "document_type": "presentation|standard",
    "folder": "relative/path",
    "taxonomy_term": "classified term (if enriched)",
    "taxonomy_id": "uuid (if enriched)"
  }
}
```

**Text Index:** Collections include a text index on `content` field for hybrid search (keyword + vector).

---

## Search Architecture — Two-Stage Retrieval

### Stage 1: Hybrid Search

Combines dense vector similarity with Qdrant text matching using weighted Reciprocal Rank Fusion (RRF). Source scoping is applied at this stage via `source_ids` filter.

```
query
  ├── dense vector search  (embedding model, cosine similarity)
  └── text keyword search  (Qdrant text index, BM25-style)
        ↓
  weighted RRF fusion  (default vector_weight=0.7)
        ↓
  candidate set  (top_k × 4 results)
```

Multiple embedding models are handled transparently: sources are grouped by their embedding config and queried independently, then merged via RRF.

### Stage 2: Cross-Encoder Reranking

Applied by default after hybrid search. Uses FlashRank (`ms-marco-MiniLM-L-12-v2`, ~34MB local cross-encoder) with Ollama `/api/rerank` as fallback.

```
candidate set
        ↓
  cross-encoder  (FlashRank ms-marco-MiniLM-L-12-v2, scores query-document pairs jointly)
        ↓
  reranked results  (top_k from candidates, _rerank_score replaces original score)
```

**Score normalization:** Scores are normalized to 0–1 range. Original retrieval score preserved as `original_score` in metadata for debugging.

**Opt-out:** Pass `rerank=false` on search requests to skip Stage 2 and return Stage 1 results directly.

**Graceful degradation:** `RerankerService` tries FlashRank first (local Python cross-encoder, auto-downloads model on first use). If unavailable, falls back to Ollama `/api/rerank`. If both fail, reranking is skipped — no crash, no repeated failed calls.

### Stage 3: Deep Search (Query Decomposition)

`deep_search` adds an automatic query decomposition stage before Stage 1. Exposed as a separate MCP tool (`agentbase_deep_search`) and REST endpoint for complex multi-part questions.

```
complex query
        ↓
  QueryDecomposer  (gemma4:e4b via Ollama, rule-based fallback)
        ↓
  2-5 focused sub-queries  (with metadata filters from taxonomy vocabulary)
        ↓
  parallel Stage 1 search  (one per sub-query, top_k × 2 candidates each)
        ↓
  dedup by content_hash → RRF fusion → Stage 2 reranking against original query
        ↓
  top_k results
```

**Taxonomy-aware:** The decomposition prompt is injected with taxonomy vocabulary (facet → values) so the LLM can extract structured metadata filters for each sub-query.

**Graceful degradation:** If Ollama is unavailable, falls back to rule-based decomposition (conjunction splitting + taxonomy term regex). Always includes the original query as a sub-query.

### Search Method Reference

| Method | Description |
|--------|-------------|
| `search_standard` | Dense vector search, single embedding model |
| `search_multi_embedding` | Vector search across sources with different embedding models, RRF merge |
| `search_hybrid` | Dense + keyword search, weighted RRF fusion |
| `search_grouped` | Vector search with results grouped by source document (max N chunks per doc) |
| `deep_search` | Query decomposition → parallel sub-query search → dedup → RRF fusion → rerank |

All methods accept an optional `rerank=True` parameter to apply Stage 2.

---

## Security Hardening

### Authentication

API key authentication with scope-based authorization. Two auth modes:

| Mode | Mechanism | Access |
|------|-----------|--------|
| `AUTH_TOKEN` | Global token (header/env) | Full access |
| `APIKey` | Per-key scopes (read/write) | Scope-limited |

IP-based access control: request source IP is validated against trusted CIDR ranges configured in settings. Requests from untrusted IPs are rejected at the middleware layer before route handlers execute.

**Key derivation:** Argon2id for new keys. SHA-256 accepted for backward compatibility with existing keys. Timing-safe comparison prevents timing attacks on key validation.

**MCP write enforcement:** All MCP tools that perform write operations call `check_mcp_scope(Scope.WRITE)` at entry. Auth state is propagated via `contextvars` (FastAPI request context is not available inside MCP tool functions).

### SSRF Protection

`core/url_validator.py` validates all user-supplied URLs before server-side fetching:

- Scheme whitelist (`http`, `https` only)
- Hostname blocklist (rejects `localhost`, `0.0.0.0`, `metadata.google.internal`, etc.)
- DNS resolution: resolves hostname to IP, then validates against blocked IPv4/IPv6 networks
- Blocked networks include RFC 1918 private ranges, loopback, link-local (AWS metadata `169.254.0.0/16`), multicast, and cloud-metadata ranges

### Additional Hardening

| Control | Implementation |
|---------|----------------|
| CORS validation | Strict origin validation, no wildcard in production |
| Magic bytes validation | File type verified against binary signature, not just extension |
| Body size limits | Request body limit enforced at middleware |
| Argon2id key hashing | Memory-hard KDF for stored API key hashes |

---

## Plugin Architecture

Enable extensibility through swappable components.

| Type | Interface | Examples |
|------|-----------|----------|
| `DocumentLoader` | `load(source) -> Document[]` | PDF/DOCX via Tika, HTML, Confluence, Notion |
| `Chunker` | `chunk(doc, config) -> Chunk[]` | Recursive, Semantic, Markdown-aware |
| `Embedder` | `embed(texts) -> Vector[]` | OpenAI, Cohere, Local models |
| `Retriever` | `search(query) -> Result[]` | Vector, Hybrid, Multi-index |
| `Reranker` | `rerank(query, docs) -> Result[]` | FlashRank (local), Ollama fallback, None |
| `LLMProvider` | `chat(messages) -> Response` | OpenAI, Anthropic, Ollama, etc. |

---

## MCP Server Interface

Model Context Protocol server mounted at `/mcp` (HTTP-based, streamable). Provides **84 tools** across 12 modules (auth, projects, agents, libraries, sources, source ops, source docs, uploads, taxonomy, evaluation, discovery, guide), all named with an `agentbase_` prefix, for AI agent access.

**Tool Domains:**

| Domain | Module | Capabilities |
|--------|--------|-------------|
| **Auth** | `mcp/tools/auth.py` | Bootstrap first API key |
| **Agents** | `mcp/tools/agents.py` | Agent CRUD, library/source bindings |
| **Sources** | `mcp/tools/sources.py` | Source management, search, upload, export, indexing |
| **Source Ops** | `mcp/tools/source_ops.py` | Analytics, refresh, re-enrich, retry-failed, watcher management |
| **Libraries** | `mcp/tools/libraries.py` | Library CRUD, source management |
| **Taxonomy** | `mcp/tools/taxonomy.py` | Taxonomy CRUD, term management, coverage analytics, suggestion review |
| **Projects** | `mcp/tools/projects.py` | Project management (deprecated — #56) |
| **Guide** | `mcp/tools/guide.py` | Workflow recipes for common goals (discoverability) |

**Write authorization:** All tools that create, update, delete, or trigger operations call `check_mcp_scope(Scope.WRITE)`. Auth state is threaded via `contextvars` from middleware to tool execution.

**Implementation:** `backend/app/mcp/` — `server.py` creates a FastMCP instance, tool modules in `mcp/tools/`.

---

## New API Modules (v2)

| Module | Path | Purpose |
|--------|------|---------|
| `watchers` | `api/sources/watchers.py` | Watcher status, start/stop per source |
| `analytics` | `api/sources/analytics.py` | System-wide statistics (coverage, stale docs, classification rates) |
| `url_validator` | `core/url_validator.py` | SSRF protection for all user-supplied URLs |
| `re_enrichment` | `services/ingestion/re_enrichment.py` | Batch reclassification of existing chunks without re-indexing |
| `reranker` | `services/rag/reranker.py` | Cross-encoder reranking via FlashRank (local) with Ollama fallback |
| `decomposer` | `services/rag/decomposer.py` | LLM + rule-based query decomposition for deep search |
| `tika` | `services/ingestion/indexers/tika.py` | Apache Tika extraction for binary documents |
| `library_chat` | `services/library_chat.py` | Stateless multi-turn chat against a Library's knowledge base via RAG + LLM |

---

## Frontend Architecture — Library Detail Page

`LibraryDetailPage.tsx` — five-tab interface for managing and interacting with a library.

### Tab Structure

| Tab | Component | Contents |
|-----|-----------|---------|
| **Sources** | `libraries/SourcesTab.tsx` | Sources attached to this library, add/remove |
| **Documents** | `libraries/DocumentsTab.tsx` | Indexed document list with search and type filters |
| **Retrieval Lab** | `libraries/retrieval-lab/RetrievalLabTab.tsx` | Side-by-side retrieval config comparison (2-3 panels) |
| **Chat** | `libraries/chat/ChatTab.tsx` | Multi-turn RAG chat with provider/model config |
| **Settings** | `libraries/SettingsTab.tsx` | Library metadata, recalculate stats, delete |

### Retrieval Lab Components

| Component | Purpose |
|-----------|---------|
| `retrieval-lab/ConfigPanel.tsx` | Per-panel search config (mode, top_k, rerank, vector weight, source filter) |
| `retrieval-lab/ResultPanel.tsx` | Results display with latency and score for one config |
| `retrieval-lab/ResultCard.tsx` | Single result card (content, score, source, title) |

### Chat Components

| Component | Purpose |
|-----------|---------|
| `chat/ChatTab.tsx` | Orchestrates conversation state, optimistic UI, error recovery |
| `chat/ChatConfig.tsx` | Provider/model picker, search mode, top_k, rerank toggles |
| `chat/ChatInput.tsx` | Multi-line input with Cmd/Ctrl+Enter submit |
| `chat/ChatMessage.tsx` | Renders user/assistant bubbles with collapsible source citations |

---

## Frontend Architecture — Sources Page

The Sources page is organized into three tabs with extracted hooks for state management.

### Tab Structure

| Tab | Component | Contents |
|-----|-----------|---------|
| **Sources** | `tabs/SourcesTab.tsx` | Source list, add/edit/delete, indexing trigger |
| **Search** | `tabs/SearchTab.tsx` | Query input, dynamic taxonomy filters, result cards |
| **Pipeline Health** | `tabs/PipelineHealthTab.tsx` | Coverage card, stale docs list, suggestions queue |

### Extracted Hooks

| Hook | File | Manages |
|------|------|---------|
| `useSources` | `hooks/useSources.ts` | Source list state, CRUD operations, polling |
| `useSourceSearch` | `hooks/useSourceSearch.ts` | Search state, filter state, result pagination |

### Pipeline Health Components

| Component | Purpose |
|-----------|---------|
| `pipeline/CoverageCard.tsx` | Classification coverage rate across all sources |
| `pipeline/StaleDocsList.tsx` | Documents not re-indexed since last file modification |
| `pipeline/SuggestionsQueue.tsx` | Pending taxonomy term suggestions for review |

### Source Configuration

`SourceConfigPanel.tsx` — inline panel showing enrichment configuration (taxonomy assignment, classification model) and watcher status (mode, last-seen event, poll interval) for directory sources.

`SearchFilters.tsx` — filter controls populated dynamically from the active taxonomy; filters collapse when no taxonomy is assigned to searched sources.

---

## Observability & Analytics

### Metrics to Capture

| Category | Metrics |
|----------|---------|
| **Usage** | Queries/day, tokens used, active users, API calls |
| **Performance** | Latency (p50, p95, p99), throughput, error rates |
| **Quality** | Retrieval relevance, user feedback, regeneration rate |
| **Pipeline** | Classification coverage, stale doc count, enrichment success rate |
| **Cost** | LLM tokens, embedding tokens, storage used |

### Analytics API

`/api/sources/analytics` provides system-wide statistics:
- Total documents indexed
- Classification coverage (% of chunks with taxonomy labels)
- Stale document count (file modified after last index)
- Suggestion queue depth

---

## Distribution Options

| Method | Use Case |
|--------|----------|
| Docker Compose | Local development, single-server deployment |
| Helm Chart | Kubernetes deployment |
| Python Package | Library usage, custom integrations |
| Pre-built Binaries | Simple local installation |

---

## API Authentication — Implemented

### API Keys with Scopes

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    name TEXT,
    key_hash TEXT,        -- Argon2id (new) or SHA-256 (legacy)
    key_prefix TEXT,
    scopes TEXT[],        -- ['read', 'write']
    expires_at TIMESTAMP,
    created_at TIMESTAMP,
    last_used_at TIMESTAMP
);
```

**Usage:**
```bash
curl -H "Authorization: Bearer as_abc123..." https://api.example.com/api/agents
```

Scopes enforce read/write separation. MCP write tools enforce `Scope.WRITE` via `check_mcp_scope()`.

### Phase 2 - Multi-Tenancy (Future)
- Tenant isolation with own projects, sources, agents
- Shared read-only sources across tenants
- Resource quotas (storage limits, API call limits, token budgets)
- OAuth2/OIDC enterprise SSO integration
- Usage billing per tenant
