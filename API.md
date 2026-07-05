# API Specification

**Version:** 2.0.0
**Base URL:** `http://localhost:8002`
**Content-Type:** `application/json` (unless otherwise specified)

---

## Overview

Agentbase exposes a RESTful API for source and library management, agent configuration, and RAG experimentation.

### Core Services

| Service | Prefix | Description |
|---------|--------|-------------|
| Health | `/health` | System health checks |
| Projects | `/api/projects` | Project management and resource assignments |
| Providers | `/api/providers` | LLM provider configuration |
| Sources | `/api/sources` | RAG source management |
| Prompts | `/api/prompts` | Prompt template management |
| Agents | `/api/agents` | AI agent CRUD and API key management |
| Experiments | `/api/experiments` | RAG experimentation framework |
| Events | `/api/events` | Server-sent events for real-time updates |
| Config | `/api/config` | System configuration |
| Taxonomy | `/api/taxonomies` | Classification taxonomies and term management |
| Libraries | `/api` | Curated document collections (Libraries) |
| Docs | `/api/docs` | API reference documentation |

**MCP Server:** An MCP (Model Context Protocol) server is mounted at `/mcp` providing 84 tools across 12 domains (Auth, Projects, Agents, Libraries, Sources, Source Ops, Source Docs, Source Upload, Taxonomy, Evaluation, Guide, Discovery). All tool names carry the `agentbase_` service prefix (e.g. `agentbase_search_sources`, `agentbase_create_library`) to prevent collisions in multi-server environments. See [ARCHITECTURE.md](./ARCHITECTURE.md) for details, and the README's "Connecting AI Agents (MCP)" section for connection setup.

---

## Health Service

### Check System Health

```
GET /health
```

Returns overall system health and provider status.

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "providers": {
    "ollama": true,
    "openai": true,
    "anthropic": true,
    "grok": false,
    "google": true
  }
}
```

---

## Projects Service

Manages project containers for organizing sources, agents, and prompts.

### List Projects

```
GET /api/projects/
```

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "My Project",
    "description": "Project description",
    "instructions": "Custom instructions for this project",
    "created_at": "2024-01-14T10:00:00Z",
    "updated_at": "2024-01-14T10:00:00Z",
    "knowledge_provider": "anthropic",
    "knowledge_model": "claude-sonnet-4-20250514"
  }
]
```

### Create Project

```
POST /api/projects/
```

**Request Body:**
```json
{
  "name": "My Project",
  "description": "Optional description"
}
```

**Response:** `201 Created` - Returns created project object

### Get Project

```
GET /api/projects/{project_id}
```

**Response:** Project object

### Update Project

```
PUT /api/projects/{project_id}
```

**Request Body:**
```json
{
  "name": "Updated Name",
  "description": "Updated description",
  "instructions": "Custom project instructions",
  "knowledge_provider": "openai",
  "knowledge_model": "gpt-4o"
}
```

All fields are optional.

**Response:** Updated project object

### Delete Project

```
DELETE /api/projects/{project_id}
```

**Response:** `204 No Content`

### List Project Sources

```
GET /api/projects/{project_id}/knowledge-sources
```

Returns both project-specific sources and assigned global sources.

**Response:**
```json
[
  {
    "id": "uuid",
    "source_id": "uuid",
    "source_name": "Documentation",
    "source_type": "url",
    "status": "indexed",
    "document_count": 150,
    "chunk_count": 1200,
    "is_global": false,
    "assigned_at": null
  }
]
```

### Assign Sources

```
POST /api/projects/{project_id}/knowledge-sources
```

Assign global sources to a project.

**Request Body:**
```json
{
  "source_ids": ["uuid1", "uuid2"]
}
```

**Response:**
```json
{
  "assigned": 2
}
```

### Unassign Sources

```
DELETE /api/projects/{project_id}/knowledge-sources
```

**Request Body:**
```json
{
  "source_ids": ["uuid1", "uuid2"]
}
```

**Response:**
```json
{
  "removed": 2
}
```

### Set Project Default Model

```
PUT /api/projects/{project_id}/default-model
```

Creates or updates a project-level model assignment that overrides the global default for agents in this project.

**Request Body:**
```json
{
  "task_type": "knowledge",
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task_type` | string | Yes | `"knowledge"` or `"embedding"` |
| `provider` | string | Yes | Provider name |
| `model` | string | Yes | Model identifier |

**Response:**
```json
{
  "status": "assigned",
  "project_id": "uuid",
  "task_type": "knowledge",
  "provider": "anthropic",
  "model": "claude-sonnet-4-20250514"
}
```

---

## Providers Service

Manages LLM provider configuration and model assignments.

### List Providers

```
GET /api/providers
```

**Response:**
```json
[
  {
    "name": "anthropic",
    "display_name": "Anthropic",
    "is_configured": true,
    "is_active": true,
    "is_healthy": true,
    "available_models": ["claude-sonnet-4-20250514", "claude-opus-4-20250514"],
    "base_url": null,
    "requires_api_key": true
  },
  {
    "name": "ollama",
    "display_name": "Ollama",
    "is_configured": true,
    "is_active": true,
    "is_healthy": true,
    "available_models": ["llama3.2", "codellama"],
    "base_url": "http://host.docker.internal:11434",
    "requires_api_key": false
  }
]
```

### Get Provider

```
GET /api/providers/{provider_name}
```

**Response:** Single provider object

### Update Provider

```
PUT /api/providers/{provider_name}
```

**Request Body:**
```json
{
  "api_key": "sk-...",
  "base_url": "https://api.example.com",
  "is_active": true
}
```

All fields are optional.

**Response:**
```json
{
  "status": "updated",
  "provider": "openai"
}
```

### Delete Provider Configuration

```
DELETE /api/providers/{provider_name}
```

Deletes the provider configuration if a database record exists, or disables the provider if it only has environment-based configuration.

**Response:**
```json
{
  "status": "deleted",
  "provider": "openai"
}
```

Or if provider only has env config:
```json
{
  "status": "disabled",
  "provider": "openai"
}
```

### Test Provider Connection

```
POST /api/providers/{provider_name}/test
```

**Response:**
```json
{
  "status": "success",
  "provider": "anthropic",
  "healthy": true,
  "message": "Connection successful",
  "model_count": 5
}
```

### List Available Models

```
GET /api/providers/models/available
```

**Response:**
```json
[
  {
    "id": "claude-sonnet-4-20250514",
    "name": "Claude Sonnet 4",
    "provider": "anthropic",
    "context_window": 200000,
    "capabilities": ["chat", "streaming"]
  }
]
```

### List Embedding Models

```
GET /api/providers/embedding-models/available
```

**Response:**
```json
[
  {
    "id": "text-embedding-3-small",
    "name": "Text Embedding 3 Small",
    "provider": "openai",
    "dimensions": 1536,
    "max_input_tokens": 8191
  }
]
```

### Get Model Assignments

```
GET /api/providers/models/assignments?project_id={uuid}
```

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | No | Filter by project (omit for global) |

**Response:**
```json
[
  {
    "task_type": "knowledge",
    "provider": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "is_global": true
  },
  {
    "task_type": "embedding",
    "provider": "openai",
    "model": "text-embedding-3-small",
    "is_global": true
  }
]
```

### Assign Model to Task

```
POST /api/providers/models/assign?project_id={uuid}
```

**Request Body:**
```json
{
  "task_type": "knowledge",
  "provider": "openai",
  "model": "gpt-4o"
}
```

**Response:**
```json
{
  "status": "assigned",
  "task_type": "knowledge",
  "provider": "openai",
  "model": "gpt-4o"
}
```

---

## Sources Service

Manages RAG sources, indexing, and semantic search.

### List Sources

```
GET /api/sources?project_id={uuid}
```

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | No | Filter by project |

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Documentation",
    "source_type": "url",
    "source_path": "https://example.com/docs",
    "project_id": "uuid",
    "status": "indexed",
    "last_indexed": "2024-01-14T10:00:00Z",
    "document_count": 150,
    "chunk_count": 1200,
    "error_message": null,
    "progress": 150,
    "progress_total": 150,
    "progress_message": "Complete: 150 pages indexed, 1200 chunks",
    "progress_updated_at": "2024-01-14T10:05:00Z",
    "embedding_provider": "openai",
    "embedding_model": "text-embedding-3-small",
    "created_at": "2024-01-14T09:00:00Z"
  }
]
```

**Source Types:**
| Type | Description |
|------|-------------|
| `directory` | Local filesystem directory |
| `url` | Web pages (with sitemap discovery) |
| `file` | Uploaded file (PDF) |

**Status Values:**
| Status | Description |
|--------|-------------|
| `pending` | Created, not yet indexed |
| `indexing` | Currently being indexed |
| `indexed` | Successfully indexed |
| `error` | Indexing failed |

### List Global Sources

```
GET /api/sources/global
```

Returns sources not associated with any project.

**Response:** Same as List Sources

### Add Source (JSON)

```
POST /api/sources
```

**Request Body:**
```json
{
  "name": "My Documentation",
  "source_type": "url",
  "source_path": "https://example.com/docs",
  "project_id": "uuid",
  "selected_urls": [
    "https://example.com/docs/page1",
    "https://example.com/docs/page2"
  ],
  "embedding_provider": "openai",
  "embedding_model": "text-embedding-3-small",
  "enrichment_enabled": false,
  "enrichment_taxonomy_id": null,
  "enrichment_model": null,
  "watch_enabled": false,
  "watch_mode": "auto",
  "watch_poll_interval_seconds": 300,
  "watch_debounce_seconds": 60,
  "watch_max_file_size_mb": 50
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name |
| `source_type` | string | Yes | `"url"`, `"directory"`, `"file"`, or `"youtube"` |
| `source_path` | string | Yes | Path, base URL, or (for `youtube`) a channel URL |
| `project_id` | string | No | Associate with project |
| `selected_urls` | array | No | For URL sources only |
| `embedding_provider` | string | No | Override default embedding provider |
| `embedding_model` | string | No | Override default embedding model |
| `enrichment_enabled` | boolean | No | Enable LLM classification on ingest (default `false`) |
| `enrichment_taxonomy_id` | string | No | Taxonomy ID to classify against |
| `enrichment_model` | string | No | Model to use for enrichment (falls back to project default) |
| `youtube_backfill_mode` | string | No | For `youtube` sources: `"all"` or `"recent"` (default `"recent"`) |
| `youtube_recent_count` | integer | No | For `youtube` sources when mode is `"recent"`: number of latest videos (default `50`) |
| `watch_enabled` | boolean | No | Enable filesystem watcher for `directory` sources (default `false`) |
| `watch_mode` | string | No | `"auto"`, `"poll"`, or `"inotify"` (default `"auto"`) |
| `watch_poll_interval_seconds` | integer | No | Polling interval in seconds (default `300`) |
| `watch_debounce_seconds` | integer | No | Delay before processing a detected change (default `60`) |
| `watch_max_file_size_mb` | integer | No | Skip files larger than this limit (default `50`) |

> **YouTube sources** (`source_type: "youtube"`): `source_path` is a channel URL
> (e.g. `https://www.youtube.com/@channelname`). Indexing enumerates the channel,
> fetches English captions per video, and stores transcripts as documents. It is
> incremental — re-indexing only fetches videos not already ingested — and
> defaults to `freshness_policy: "automatic"` with a daily refresh so new uploads
> are picked up. Videos without captions are skipped.

**Response:** `201 Created` - Returns source object

### Upload File Source

```
POST /api/sources/upload
Content-Type: multipart/form-data
```

**Form Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | Yes | PDF file (max 50MB) |
| `name` | string | Yes | Display name |
| `project_id` | string | No | Associate with project |

**Response:** `201 Created` - Returns source object (indexing starts automatically)

### Adopt Orphaned Collection

```
POST /api/sources/adopt
```

Create a source record for an existing Qdrant collection.

**Request Body:**
```json
{
  "collection_name": "kb_docs_abc123",
  "name": "Recovered Collection",
  "project_id": "uuid"
}
```

**Response:** `201 Created` - Returns source object

### Get Source

```
GET /api/sources/{source_id}
```

**Response:** Source object

### Update Source

```
PUT /api/sources/{source_id}
```

All fields are optional. Changing `watch_enabled` automatically starts or stops the watcher.

**Request Body:**
```json
{
  "name": "Updated Name",
  "description": "Updated description",
  "watch_enabled": true,
  "watch_mode": "poll",
  "watch_poll_interval_seconds": 600,
  "watch_debounce_seconds": 30,
  "watch_max_file_size_mb": 100,
  "enrichment_enabled": true,
  "enrichment_taxonomy_id": "uuid",
  "enrichment_model": "ollama/llama3.2"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name |
| `description` | string | Source description |
| `watch_enabled` | boolean | Enable/disable filesystem watcher |
| `watch_mode` | string | `"auto"`, `"poll"`, or `"inotify"` |
| `watch_poll_interval_seconds` | integer | Polling interval in seconds |
| `watch_debounce_seconds` | integer | Delay before processing changes |
| `watch_max_file_size_mb` | integer | Skip files larger than this |
| `enrichment_enabled` | boolean | Enable/disable LLM classification |
| `enrichment_taxonomy_id` | string | Taxonomy ID for classification |
| `enrichment_model` | string | Model for enrichment |

**Response:** Updated source object

### Add Files to Source

```
POST /api/sources/{source_id}/files
Content-Type: multipart/form-data
```

Upload additional files to an existing source.

**Form Fields:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `files` | file[] | Yes | One or more files to add |

**Response:** Updated source object (indexing starts automatically)

### Remove Files from Source

```
DELETE /api/sources/{source_id}/files
```

**Request Body:**
```json
{
  "file_paths": ["file1.pdf", "file2.pdf"]
}
```

**Response:** Updated source object

### Delete Source

```
DELETE /api/sources/{source_id}
```

Deletes the source, its Qdrant collection, and uploaded file (if applicable).

**Response:** `204 No Content`

### Trigger Indexing

```
POST /api/sources/{source_id}/index
```

Starts background indexing task.

**Response:**
```json
{
  "status": "indexing",
  "source_id": "uuid",
  "message": "Indexing started in background"
}
```

### Get Indexing Status

```
GET /api/sources/{source_id}/status
```

**Response:**
```json
{
  "source_id": "uuid",
  "status": "indexing",
  "progress": 45,
  "progress_total": 150,
  "progress_message": "Scraping (45/150): https://example.com/docs/page45",
  "progress_updated_at": "2024-01-14T10:02:30Z",
  "document_count": 44,
  "chunk_count": 352,
  "error_message": null
}
```

### Refresh Source

```
POST /api/sources/{source_id}/refresh
```

Re-indexes the source, refreshing all content.

**Response:** Same as Trigger Indexing

### Re-Enrich Source

```
POST /api/sources/{source_id}/re-enrich
```

Triggers a background job to re-classify all existing Qdrant chunks for a source using LLM enrichment. The source must already be indexed and have an `enrichment_taxonomy_id` configured.

**Response:**
```json
{
  "status": "queued",
  "source_id": "uuid",
  "job_id": "uuid",
  "message": "Re-enrichment job queued"
}
```

> Track progress via `GET /api/jobs/{job_id}`. Returns `400` if the source has no collection or no taxonomy configured.

### Get Indexing Logs

```
GET /api/sources/{source_id}/logs?status_filter={status}&limit=500
```

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status_filter` | string | - | Filter by status |
| `limit` | integer | `500` | Max logs to return |

**Response:**
```json
{
  "logs": [
    {
      "id": "uuid",
      "source_id": "uuid",
      "url": "https://example.com/docs/page1",
      "status": "done",
      "error_message": null,
      "scrape_duration_ms": 1250,
      "embed_duration_ms": 450,
      "content_length": 15000,
      "chunk_count": 12,
      "created_at": "2024-01-14T10:00:00Z",
      "updated_at": "2024-01-14T10:00:02Z"
    }
  ],
  "summary": {
    "total": 150,
    "done": 145,
    "failed": 3,
    "skipped": 0,
    "pending": 0,
    "in_progress": 2
  }
}
```

**Log Status Values:**
| Status | Description |
|--------|-------------|
| `pending` | Queued for processing |
| `scraping` | Currently being scraped |
| `scraped` | Scraped, awaiting embedding |
| `embedding` | Currently being embedded |
| `done` | Successfully indexed |
| `failed` | Processing failed |
| `skipped` | Skipped (e.g., duplicate) |

### Retry Failed URLs

```
POST /api/sources/{source_id}/retry-failed
```

Retries only URLs with `failed` status.

**Response:**
```json
{
  "status": "indexing",
  "source_id": "uuid",
  "message": "Retrying 3 failed URLs",
  "retry_count": 3
}
```

### Clear Indexing Logs

```
DELETE /api/sources/{source_id}/logs
```

**Response:** `204 No Content`

### Add URLs to Source

```
POST /api/sources/{source_id}/urls
```

Add additional URLs to an existing source.

**Request Body:**
```json
{
  "urls": ["https://example.com/new-page1", "https://example.com/new-page2"]
}
```

**Response:**
```json
{
  "added": 2
}
```

### Remove URLs from Source

```
DELETE /api/sources/{source_id}/urls
```

**Request Body:**
```json
{
  "urls": ["https://example.com/page-to-remove"]
}
```

**Response:**
```json
{
  "removed": 1
}
```

### Scan URL Structure

```
POST /api/sources/scan-url
```

Stage 1 of URL source creation: discovers pages for selection.

**Request Body:**
```json
{
  "url": "https://example.com/docs",
  "max_depth": 2,
  "path_scope": "/docs",
  "sitemap_url": null,
  "path_filter": "/docs/guide/",
  "auto_discover_sitemap": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | - | Base URL to scan |
| `max_depth` | integer | `2` | Crawl depth (crawl mode) |
| `path_scope` | string | - | Limit crawl to path prefix |
| `sitemap_url` | string | - | Explicit sitemap URL |
| `path_filter` | string | - | Filter sitemap URLs by path |
| `auto_discover_sitemap` | boolean | `false` | Auto-discover sitemap from robots.txt |

**Scanning Modes:**
1. **Auto-discover** (`auto_discover_sitemap: true`): Checks robots.txt and common locations
2. **Sitemap** (`sitemap_url` provided): Parses specified sitemap
3. **Crawl** (default): Follows links on pages up to `max_depth`

**Response:**
```json
{
  "tree": {
    "url": "https://example.com/docs",
    "title": "Documentation",
    "path": "/docs",
    "children": [
      {
        "url": "https://example.com/docs/getting-started",
        "title": "Getting Started",
        "path": "/docs/getting-started",
        "children": []
      }
    ]
  },
  "sitemap_url": "https://example.com/sitemap.xml"
}
```

### Semantic Search

```
POST /api/sources/search
```

**Request Body:**
```json
{
  "query": "How do I configure authentication?",
  "project_id": "uuid",
  "top_k": 5,
  "hybrid": true,
  "vector_weight": 0.7,
  "source_ids": ["uuid1", "uuid2"],
  "filters": {"doc_category": "guide"},
  "rerank": true,
  "include_neighbors": 0
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | - | Search query |
| `project_id` | string | - | Limit to project's sources |
| `top_k` | integer | `5` | Number of results |
| `hybrid` | boolean | `true` | Use hybrid search (vector + keyword) |
| `vector_weight` | float | `0.7` | Vector vs. keyword weight (0–1, hybrid only) |
| `source_ids` | array | - | Restrict search to specific source IDs |
| `knowledge_base_id` | string | - | Search all sources in a Library. Mutually exclusive with `source_ids` |
| `filters` | object | - | Metadata filters (AND across keys, OR within lists). Keys: `platforms`, `products`, `offerings`, `doc_category`, `companies`, `topics`, `document_type`, `file_type` |
| `rerank` | boolean | `true` | Apply cross-encoder reranking after retrieval (set `false` to skip) |
| `include_neighbors` | integer | `0` | Include neighboring chunks for context (1 = +/-1 chunk, 2 = +/-2, etc.) |

**Response:**
```json
[
  {
    "content": "Chunk content text...",
    "source": "https://example.com/docs/auth",
    "score": 0.89,
    "title": "Authentication Guide",
    "source_name": "Documentation",
    "document_path": "https://example.com/docs/auth",
    "collection": "kb_docs_abc123",
    "rerank_score": 0.92,
    "metadata": {
      "source_id": "uuid",
      "chunk_index": 3,
      "classification": {"platforms": ["AcmeCRM"], "doc_category": "guide"}
    },
    "context_chunks": [
      {"chunk_index": 2, "content": "Previous chunk..."},
      {"chunk_index": 3, "content": "Matched chunk..."},
      {"chunk_index": 4, "content": "Next chunk..."}
    ]
  }
]
```

> `context_chunks` only present when `include_neighbors > 0`. `rerank_score` only present when `rerank=true`.

### Deep Search (Query Decomposition)

```
POST /api/sources/deep-search
```

Deep search with automatic query decomposition for complex, multi-part questions. Breaks the query into focused sub-queries, searches each in parallel, deduplicates, fuses via RRF, and reranks against the original query.

**Request Body:**
```json
{
  "query": "How does AcmeCRM handle email personalization and what are the Acme Data Hub integration capabilities?",
  "top_k": 10,
  "max_sub_queries": 5,
  "source_ids": ["uuid1"],
  "filters": {"platforms": ["AcmeCRM"]},
  "rerank": true,
  "include_decomposition": true
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `query` | string | - | The complex search query |
| `top_k` | integer | `10` | Number of final results (max 50) |
| `max_sub_queries` | integer | `5` | Max sub-queries from decomposition (max 10, excludes the original query which is always included) |
| `source_ids` | array | - | Restrict search to specific source IDs |
| `knowledge_base_id` | string | - | Search all sources in a Library. Mutually exclusive with `source_ids` |
| `filters` | object | - | Global metadata filters applied to ALL sub-queries (same format as `/search`) |
| `rerank` | boolean | `true` | Apply cross-encoder reranking on merged results |
| `include_decomposition` | boolean | `false` | Include sub-queries in response for transparency/debugging |

**Response:**
```json
{
  "results": [
    {
      "content": "AcmeCRM Engagement, including its journey builder...",
      "source": "file.pdf",
      "score": 0.9932,
      "title": "ACME RFP Response",
      "source_name": "Client Proposals",
      "document_path": "file.pdf",
      "collection": "kb_proposals_abc123",
      "rerank_score": 0.9932,
      "metadata": { "source_id": "uuid", "chunk_index": 3, "fusion_method": "rrf" }
    }
  ],
  "sub_queries": [
    {"query": "AcmeCRM email personalization features", "filters": {"product": "AcmeCRM"}, "strategy": "aspect"},
    {"query": "Acme Data Hub integration capabilities", "filters": {"product": "Acme Data Hub"}, "strategy": "aspect"},
    {"query": "How does AcmeCRM handle email personalization and...", "filters": {}, "strategy": "original"}
  ],
  "stats": {
    "sub_query_count": 3,
    "total_candidates": 30,
    "deduplicated": 26,
    "returned": 5,
    "decomposition_time_ms": 1500,
    "search_time_ms": 1200,
    "rerank_time_ms": 800,
    "total_time_ms": 3500
  }
}
```

> `sub_queries` only present when `include_decomposition=true`. Strategy values: `entity`, `aspect`, `temporal`, `abstraction`, `original`.

### Get All Watcher Statuses

```
GET /api/sources/watchers/status
```

Returns status of all active directory source file watchers.

**Response:**
```json
{
  "watchers": {
    "uuid-source-1": {
      "source_id": "uuid-source-1",
      "running": true,
      "mode": "poll",
      "last_sync_at": "2024-01-14T10:05:00Z"
    }
  }
}
```

### Get Watcher Status

```
GET /api/sources/watchers/status/{source_id}
```

Returns status for a single source's watcher. Returns `404` if no active watcher exists for this source.

**Response:** Single watcher status object (same shape as values in the map above)

### Start Watcher

```
POST /api/sources/watchers/{source_id}/start
```

Starts the filesystem watcher for a directory source. The source must have `watch_enabled = true` and `source_type = "directory"`.

**Response:**
```json
{
  "status": "started",
  "source_id": "uuid"
}
```

### Stop Watcher

```
POST /api/sources/watchers/{source_id}/stop
```

Stops the filesystem watcher for a directory source.

**Response:**
```json
{
  "status": "stopped",
  "source_id": "uuid"
}
```

### Force Directory Sync

```
POST /api/sources/watchers/{source_id}/sync
```

Forces an immediate full directory scan for a source, detecting any file additions, changes, or removals without waiting for the next poll interval.

**Response:**
```json
{
  "added": 3,
  "removed": 1,
  "unchanged": 42
}
```

### Get Source Analytics

```
GET /api/sources/analytics
```

Returns comprehensive system-wide statistics about sources and libraries. Counts are SQL-aggregate based for speed; Qdrant point counts query the Qdrant API directly.

**Response:**
```json
{
  "summary": {
    "total_sources": 12,
    "indexed_sources": 10,
    "total_documents": 850,
    "total_chunks": 6200,
    "total_qdrant_points": 6200,
    "libraries": 3,
    "active_watchers": 2,
    "sources_with_enrichment": 4
  },
  "sources_by_type": {
    "url": 5,
    "directory": 4,
    "file": 3
  },
  "sources_by_status": {
    "indexed": 10,
    "pending": 1,
    "error": 1
  },
  "top_sources": [
    { "name": "Work Documents", "chunks": 1800, "documents": 240 }
  ],
  "embedding_models": {
    "openai/text-embedding-3-small": 8,
    "ollama/mxbai-embed-large": 4
  },
  "classification_coverage": {
    "classified_chunks": 4100,
    "total_chunks": 6200,
    "coverage_percent": 66.1
  },
  "storage": {
    "qdrant_collections": 15,
    "total_qdrant_points": 6200
  }
}
```

### List Qdrant Collections

```
GET /api/sources/collections
```

**Response:**
```json
{
  "collections": [
    { "name": "kb_docs_abc123" },
    { "name": "kb_guides_def456" }
  ]
}
```

### Sources Health Check

```
GET /api/sources/health
```

**Response:**
```json
{
  "qdrant": {
    "healthy": true,
    "message": "Connected, 4 collections",
    "url": "http://host.docker.internal:6333"
  }
}
```

---

## Libraries Service

Manages curated document collections (Libraries) that aggregate multiple sources and provide a single Qdrant collection for agent retrieval.

### List Libraries

```
GET /api/libraries?project_id={uuid}
```

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Work Documents",
    "description": "All internal work docs",
    "project_id": "uuid",
    "collection_name": "agentbase_kb_work_docs_abc123",
    "embedding_provider": "openai",
    "embedding_model": "text-embedding-3-small",
    "embedding_dimensions": 1536,
    "status": "active",
    "source_count": 5,
    "document_count": 120,
    "chunk_count": 850,
    "created_at": "2024-01-14T10:00:00Z",
    "updated_at": "2024-01-14T10:05:00Z",
    "source_ids": ["source-uuid-1", "source-uuid-2"]
  }
]
```

### Create Library

```
POST /api/libraries
```

**Request Body:**
```json
{
  "name": "Work Documents",
  "description": "Optional description",
  "project_id": "uuid",
  "embedding_provider": "openai",
  "embedding_model": "text-embedding-3-small",
  "embedding_dimensions": 1536,
  "taxonomy_id": "uuid",
  "enrichment_model": "ollama/llama3.2"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Display name |
| `embedding_provider` | string | Yes | Provider for the backing Qdrant collection |
| `embedding_model` | string | Yes | Embedding model for the collection |
| `description` | string | No | Optional description |
| `project_id` | string | No | Associate with project |
| `embedding_dimensions` | integer | No | Vector size (inferred if omitted) |
| `taxonomy_id` | string | No | Taxonomy for LLM enrichment classification |
| `enrichment_model` | string | No | Model to use for enrichment |

**Response:** `201 Created` - Returns library object

### Get Library

```
GET /api/libraries/{library_id}
```

**Response:** Library object

### Update Library

```
PATCH /api/libraries/{library_id}
```

All fields are optional.

**Request Body:**
```json
{
  "name": "Updated Name",
  "description": "Updated description",
  "taxonomy_id": "uuid",
  "enrichment_model": "ollama/llama3.2",
  "status": "active"
}
```

**Response:** Updated library object

### Delete Library

```
DELETE /api/libraries/{library_id}
```

Deletes the library record and its backing Qdrant collection.

**Response:** `204 No Content`

### List Library Sources

```
GET /api/libraries/{library_id}/sources
```

Returns full details for all sources attached to this library.

**Response:** List of `SourceResponse` objects (same schema as Sources Service)

### Add Source to Library

```
POST /api/libraries/{library_id}/sources
```

**Request Body:**
```json
{
  "source_id": "uuid"
}
```

**Response:** `204 No Content`

### Remove Source from Library

```
DELETE /api/libraries/{library_id}/sources/{source_id}
```

**Response:** `204 No Content`

### Recalculate Library Stats

```
POST /api/libraries/{library_id}/recalculate-stats
```

Recounts source, document, and chunk totals for the library from the database. Use after bulk operations that may leave counters out of sync.

**Response:** Updated library object

### List Library Documents

```
GET /api/libraries/{library_id}/documents?source_id={uuid}&limit=50&offset=0&q={text}
```

Lists documents stored in the library (paginated).

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_id` | string | - | Filter by source |
| `limit` | integer | `50` | Max results per page |
| `offset` | integer | `0` | Pagination offset |
| `q` | string | - | Title/content substring search |

**Response:**
```json
[
  {
    "id": "uuid",
    "knowledge_base_id": "uuid",
    "source_id": "uuid",
    "document_id": "uuid",
    "title": "Getting Started Guide",
    "file_path": "/uploads/abc123.pdf",
    "url": null,
    "file_type": "pdf",
    "text_length": 12500,
    "content_hash": "sha256:...",
    "document_type": "guide",
    "chunk_count": 18,
    "status": "indexed",
    "error_message": null,
    "indexed_at": "2024-01-14T10:05:00Z",
    "created_at": "2024-01-14T10:00:00Z",
    "updated_at": "2024-01-14T10:05:00Z"
  }
]
```

### Get Library Document

```
GET /api/libraries/{library_id}/documents/{doc_id}
```

Returns document metadata. Full text is excluded — use `/text` for that.

**Response:** Document object (same schema as list above)

### Get Library Document Text

```
GET /api/libraries/{library_id}/documents/{doc_id}/text
```

Returns the full stored text for a document.

**Response:**
```json
{
  "doc_id": "uuid",
  "full_text": "Full document text content..."
}
```

### Delete Library Document

```
DELETE /api/libraries/{library_id}/documents/{doc_id}
```

Deletes the document record from the database. Qdrant chunk cleanup is not performed automatically — callers are responsible for removing corresponding vectors from the collection.

**Response:** `204 No Content`

---

### Chat with Library

```
POST /api/libraries/{library_id}/chat
```

Send a message and receive a grounded answer from the library's knowledge base. Stateless multi-turn: pass previous turns via `history`. Rate limited to 30 requests/minute.

**Request Body:**
```json
{
  "message": "What are the authentication options?",
  "history": [
    {"role": "user", "content": "Tell me about the platform"},
    {"role": "assistant", "content": "Agentbase is a..."}
  ],
  "config": {
    "provider": "ollama",
    "model": "gemma4:26b",
    "top_k": 5,
    "rerank": false,
    "search_mode": "hybrid",
    "vector_weight": 0.7,
    "system_prompt": null
  }
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `message` | string | — | User message (max 8000 chars) |
| `history` | array | `[]` | Prior turns — objects with `role` ("user"\|"assistant") and `content` |
| `config.provider` | string | — | **Required.** LLM provider name (e.g., `"anthropic"`, `"openai"`, `"ollama"`) |
| `config.model` | string | — | **Required.** Model name within the provider |
| `config.top_k` | integer | `5` | Chunks to retrieve for context |
| `config.rerank` | boolean | `false` | Apply cross-encoder reranking to retrieved chunks |
| `config.search_mode` | string | `"hybrid"` | `"hybrid"` \| `"vector"` \| `"deep"` (deep uses query decomposition) |
| `config.vector_weight` | float | `0.7` | Vector vs. keyword weight for hybrid mode (0-1) |
| `config.system_prompt` | string | null | Override default system prompt |

**Response:**
```json
{
  "answer": "The platform supports API key authentication with read/write scopes...",
  "sources": [
    {
      "source_id": "uuid",
      "source_name": "Documentation",
      "url": "https://example.com/docs/auth",
      "title": "Authentication Guide",
      "score": 0.89,
      "preview": "API key authentication with scope-based authorization..."
    }
  ],
  "model": "ollama/gemma4:26b"
}
```

> Returns `400` if `provider` or `model` are missing, if the library is not found, or if the provider is not configured. Returns `500` on LLM call failure.

---

## Taxonomy Service

Manages classification taxonomies for LLM-powered enrichment. A taxonomy defines a set of facets and terms used to classify document chunks during or after indexing.

### List Taxonomies

```
GET /api/taxonomies?project_id={uuid}
```

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Document Classification",
    "description": "Classifies documents by type and platform",
    "project_id": null,
    "version": 3,
    "term_count": 24,
    "created_at": "2024-01-14T10:00:00Z",
    "updated_at": "2024-01-14T10:00:00Z"
  }
]
```

### Create Taxonomy

```
POST /api/taxonomies
```

**Request Body:**
```json
{
  "name": "Document Classification",
  "description": "Optional description",
  "project_id": null
}
```

**Response:** `201 Created` - Returns taxonomy object

### Get Taxonomy

```
GET /api/taxonomies/{taxonomy_id}
```

**Response:** Taxonomy object

### Update Taxonomy

```
PATCH /api/taxonomies/{taxonomy_id}
```

**Request Body:**
```json
{
  "name": "Updated Name",
  "description": "Updated description"
}
```

**Response:** Updated taxonomy object

### Delete Taxonomy

```
DELETE /api/taxonomies/{taxonomy_id}
```

Deletes the taxonomy and all its terms and suggestions.

**Response:** `204 No Content`

---

### List Terms

```
GET /api/taxonomies/{taxonomy_id}/terms?facet={facet}
```

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `facet` | string | No | Filter to a specific facet |

**Response:**
```json
[
  {
    "id": "uuid",
    "taxonomy_id": "uuid",
    "facet": "doc_category",
    "value": "proposal",
    "parent_value": null,
    "keywords": ["rfp", "bid", "offer"],
    "sort_order": 0,
    "created_at": "2024-01-14T10:00:00Z"
  }
]
```

### Add Term

```
POST /api/taxonomies/{taxonomy_id}/terms
```

**Request Body:**
```json
{
  "facet": "doc_category",
  "value": "proposal",
  "keywords": ["rfp", "bid"],
  "sort_order": 0
}
```

**Response:** `201 Created` - Returns created term object

### Update Term

```
PATCH /api/taxonomies/{taxonomy_id}/terms/{term_id}
```

**Request Body:**
```json
{
  "keywords": ["rfp", "bid", "quote"],
  "sort_order": 1,
  "is_active": true
}
```

All fields are optional.

**Response:** Updated term object

### Delete Term

```
DELETE /api/taxonomies/{taxonomy_id}/terms/{term_id}
```

**Response:** `204 No Content`

---

### Get Coverage Analytics

```
GET /api/taxonomies/{taxonomy_id}/coverage?source_id={uuid}
```

Returns classification coverage statistics: classified vs. unclassified chunk counts, per-facet and per-term breakdowns.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_id` | string | No | Restrict analysis to a specific source |

**Response:**
```json
{
  "total_chunks": 6200,
  "classified_chunks": 4100,
  "unclassified_chunks": 2100,
  "coverage_percent": 66.1,
  "by_facet": {
    "doc_category": { "proposal": 800, "guide": 1200 }
  }
}
```

### List Stale Documents

```
GET /api/taxonomies/{taxonomy_id}/stale?source_id={uuid}&limit=100
```

Returns documents that were classified with an older version of the taxonomy and need re-enrichment.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `source_id` | string | - | Filter to a specific source |
| `limit` | integer | `100` | Max results (1–500) |

**Response:**
```json
[
  {
    "id": "uuid",
    "source_id": "uuid",
    "file_id": "https://example.com/docs/guide",
    "title": "Getting Started",
    "classification": {"doc_category": "guide"},
    "classification_taxonomy_version": 1,
    "updated_at": "2024-01-10T08:00:00Z"
  }
]
```

### Count Stale Documents

```
GET /api/taxonomies/{taxonomy_id}/stale/count?source_id={uuid}
```

**Response:**
```json
{ "count": 47 }
```

---

### List Suggestions

```
GET /api/taxonomies/{taxonomy_id}/suggestions?status=pending&limit=50
```

Lists term suggestions generated by the LLM during enrichment, sorted by frequency.

**Query Parameters:**
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | `"pending"` | `"pending"`, `"approved"`, `"rejected"`, or `"merged"` |
| `limit` | integer | `50` | Max results (1–200) |

**Response:**
```json
[
  {
    "id": "uuid",
    "taxonomy_id": "uuid",
    "facet": "doc_category",
    "suggested_value": "case_study",
    "frequency": 12,
    "sample_document_ids": ["doc-uuid-1", "doc-uuid-2"],
    "status": "pending",
    "merged_into": null,
    "created_at": "2024-01-14T10:00:00Z",
    "reviewed_at": null
  }
]
```

### Approve Suggestion

```
POST /api/taxonomies/{taxonomy_id}/suggestions/{suggestion_id}/approve
```

Creates the suggested value as a new term in the taxonomy.

**Response:** Newly created term object

### Reject Suggestion

```
POST /api/taxonomies/{taxonomy_id}/suggestions/{suggestion_id}/reject
```

Marks the suggestion as rejected.

**Response:** Updated suggestion object

### Merge Suggestion

```
POST /api/taxonomies/{taxonomy_id}/suggestions/{suggestion_id}/merge
```

Merges the suggestion into an existing term by adding it as a keyword alias.

**Request Body:**
```json
{
  "merge_into_value": "proposal"
}
```

**Response:** Updated suggestion object

---

## Prompts Service

Manages prompt templates for different task types.

### List Prompts

```
GET /api/prompts/prompts?task_type={type}&project_id={uuid}
```

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `task_type` | string | No | Filter by task type |
| `project_id` | string | No | Filter by project |

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Knowledge Assistant",
    "description": "General knowledge retrieval prompt",
    "content": "You are a helpful assistant...",
    "task_type": "knowledge",
    "is_default": true,
    "project_id": null,
    "created_at": "2024-01-14T10:00:00Z",
    "updated_at": "2024-01-14T10:00:00Z"
  }
]
```

### Create Prompt

```
POST /api/prompts/prompts
```

**Request Body:**
```json
{
  "name": "Custom Prompt",
  "description": "My custom prompt template",
  "content": "You are an expert in...",
  "task_type": "knowledge",
  "is_default": false,
  "project_id": "uuid"
}
```

**Response:** `201 Created` - Returns created prompt object

### Get Prompt

```
GET /api/prompts/prompts/{prompt_id}
```

**Response:** Prompt object

### Update Prompt

```
PUT /api/prompts/prompts/{prompt_id}
```

**Request Body:**
```json
{
  "name": "Updated Name",
  "content": "Updated content..."
}
```

**Response:** Updated prompt object

### Delete Prompt

```
DELETE /api/prompts/prompts/{prompt_id}
```

**Response:** `204 No Content`

### Duplicate Prompt

```
POST /api/prompts/prompts/{prompt_id}/duplicate
```

**Response:** `201 Created` - Returns duplicated prompt object

### Get Default Prompt

```
GET /api/prompts/prompts/default/{task_type}
```

**Response:** Default prompt for the specified task type

### List Task Types

```
GET /api/prompts/prompts/task-types
```

**Response:**
```json
["knowledge"]
```

---

## Agents Service

Manages AI agent configuration, source and library bindings, and API keys.

### List Agents

```
GET /api/agents
```

**Response:**
```json
[
  {
    "id": "uuid",
    "name": "Requirements Analyzer",
    "description": "Analyzes campaign requirements",
    "system_prompt": "You are an expert at analyzing...",
    "model_provider": "anthropic",
    "model_name": "claude-sonnet-4-20250514",
    "temperature": 0.7,
    "use_rag": true,
    "rag_top_k": 5,
    "is_public": false,
    "has_api_key": false,
    "knowledge_source_ids": ["uuid1", "uuid2"],
    "created_at": "2024-01-14T10:00:00Z",
    "updated_at": "2024-01-14T10:00:00Z"
  }
]
```

### Create Agent

```
POST /api/agents
```

**Request Body:**
```json
{
  "name": "My Agent",
  "description": "Agent description",
  "system_prompt": "You are a helpful assistant...",
  "model_provider": "anthropic",
  "model_name": "claude-sonnet-4-20250514",
  "temperature": 0.7,
  "use_rag": true,
  "rag_top_k": 5,
  "is_public": false,
  "knowledge_source_ids": []
}
```

**Response:** `201 Created` - Returns agent object

### Get Agent

```
GET /api/agents/{agent_id}
```

**Response:** Agent object

### Update Agent

```
PUT /api/agents/{agent_id}
```

**Request Body:** Same as create (all fields optional)

**Response:** Updated agent object

### Delete Agent

```
DELETE /api/agents/{agent_id}
```

**Response:** `204 No Content`

### Duplicate Agent

```
POST /api/agents/{agent_id}/duplicate
```

**Response:** `201 Created` - Returns duplicated agent object

> **Note:** Returns `403 Forbidden` for external requests (via tunnel).

### Create Agent API Key

```
POST /api/agents/{agent_id}/api-key
```

Generate an API key for programmatic agent access.

Generates a new API key (or regenerates if one already exists).

**Response:**
```json
{
  "api_key": "as_abc123...",
  "message": "API key generated",
  "has_api_key": true
}
```

---

## Experiments Service

Library-scoped pipeline experiments: clone an agent's config with overrides,
compare against baseline on a question set, promote the winner. Index
experiments (chunking/embedding shadow rebuilds) arrive in a later release.
Full design: `docs/evaluation-experiments-design.md`.

### Create Experiment

```http
POST /api/experiments
Content-Type: application/json

{
  "library_id": "lib-uuid",
  "agent_id": "agent-uuid",
  "name": "Lower temperature",
  "description": "Does temperature 0.2 reduce hallucinated steps?",
  "overrides": {"temperature": 0.2, "rag_top_k": 8}
}
```

Overridable keys (agent fields, verbatim): `system_prompt`, `model_provider`,
`model_name`, `temperature`, `rag_top_k`. Unknown keys are rejected with the
offending key named. Pipeline experiments are `status: "ready"` immediately —
no indexing.

### List / Get / Delete

```http
GET    /api/experiments?library_id={id}&agent_id={id}
GET    /api/experiments/{id}
DELETE /api/experiments/{id}
```

### Compare Against Baseline (background jobs)

```http
POST /api/experiments/{id}/compare
Content-Type: application/json

{"question_set_id": "qs-uuid"}
```

**Response (202):** `{"baseline_run_id": "...", "experiment_run_id": "..."}` —
two scorecard runs (baseline = the experiment's agent as configured today;
experiment = with overrides applied). Poll `/api/evaluation/runs/{id}` or
listen for `evaluation.run_completed` SSE events.

### Comparison Verdict

```http
GET /api/experiments/{id}/comparison?baseline_run_id={id}&experiment_run_id={id}
```

**Response:**

```json
{
  "verdict_counts": {"improved": 12, "regressed": 2, "unchanged": 9},
  "uncomparable": 1,
  "metric_deltas": {"found_at_5_rate": 0.08, "mrr": 0.05,
                    "avg_judge_scores": {"relevance": 0.04, "accuracy": 0.07, "groundedness": 0.02},
                    "latency_p50_ms": -35.0},
  "per_question": [
    {"question_id": "q-uuid", "question_text": "...", "verdict": "improved",
     "baseline": {"judge_scores": {}, "retrieval_metrics": {}, "passed": false},
     "experiment": {"judge_scores": {}, "retrieval_metrics": {}, "passed": true}}
  ]
}
```

Verdict rule: judge-score mean delta beyond 0.1, any retrieval change
(found@10 flip, best-rank move), or a passed flip. Any regression signal
classifies the question as `regressed` (conservative). `409` if either run is
still in progress.

### Promote

```http
POST /api/experiments/{id}/promote
```

Writes the experiment's overrides into the agent's live configuration, sets
status `promoted`, and emits the `evaluation.experiment_promoted` SSE event.
`409` unless the experiment is `ready`.


## Evaluation Service

Library-owned golden question sets for scoring retrieval and answer quality.
Full design: `docs/evaluation-experiments-design.md`. Scorecard runs and
experiment comparison endpoints land in upcoming releases.

### List Question Sets

```http
GET /api/evaluation/question-sets?library_id={library_id}
```

**Response:**

```json
[
  {
    "id": "qs-uuid",
    "library_id": "lib-uuid",
    "name": "ACME core questions",
    "description": "Golden questions for the ACME product docs",
    "question_counts": {"active": 12, "draft": 3},
    "created_at": "2026-06-11T10:00:00",
    "updated_at": "2026-06-11T10:00:00"
  }
]
```

### Create Question Set

```http
POST /api/evaluation/question-sets
Content-Type: application/json

{
  "library_id": "lib-uuid",
  "name": "ACME core questions",
  "description": "Golden questions for the ACME product docs"
}
```

### Get Question Set (with questions)

```http
GET /api/evaluation/question-sets/{set_id}
```

Returns the set plus its `questions` array. Question statuses: `draft`
(generated, awaiting curation), `active` (scored in runs), `archived`,
`stale` (expected document no longer exists).

### Update / Delete Question Set

```http
PATCH  /api/evaluation/question-sets/{set_id}    {"name": "...", "description": "..."}
DELETE /api/evaluation/question-sets/{set_id}
```

Deleting a set also deletes its eval runs and results.

### Add Question (manual — created active)

```http
POST /api/evaluation/question-sets/{set_id}/questions
Content-Type: application/json

{
  "question_text": "What are the three stages of ACME onboarding?",
  "expected_criteria": "Names all three stages in order",
  "expected_document_ids": ["doc-uuid"],
  "tags": ["onboarding"]
}
```

### Update Question (curation)

```http
PATCH /api/evaluation/questions/{question_id}
Content-Type: application/json

{"status": "active"}
```

Approve a draft with `status: "active"`. PATCH semantics: omitted fields are
untouched; optional fields sent as `null` are cleared.

### Delete Question

```http
DELETE /api/evaluation/questions/{question_id}
```

**Response:** `{"outcome": "deleted"}` — or `{"outcome": "archived"}` when the
question has eval results (history is preserved, the question is archived
instead).

### Generate Questions (background job)

```http
POST /api/evaluation/question-sets/{set_id}/generate
Content-Type: application/json

{"count": 30}
```

**Body fields (all optional):** `count` — total draft questions to generate
(5-50, default 30; when set it overrides `doc_sample_size` and caps the
total); `questions_per_doc` (1-10, default 3); `doc_sample_size` (1-100,
default 10, ignored when `count` is set).

**Response (202):**

```json
{"job_id": "job-uuid", "status": "queued"}
```

Drafts questions from the library's own documents using the
`question_generation` prompt task type (editable in Prompt Studio); sampling
stratifies across taxonomy classifications when present. Emits the
`evaluation.questions_generated` SSE event on completion. Generated questions
arrive as `draft` for curation.

### Run a Scorecard (background job)

```http
POST /api/evaluation/runs
Content-Type: application/json

{
  "target_type": "library",
  "target_id": "lib-uuid",
  "question_set_id": "qs-uuid"
}
```

**Response (202):** `{"run_id": "run-uuid", "status": "pending"}`

`target_type: "library"` grades retrieval only (found@5/found@10, MRR, latency
— objective, no LLM). `target_type: "agent"` runs each question through the
agent's full pipeline and adds LLM-judged answer scores (relevance, accuracy,
groundedness, pass/fail) using the `answer_evaluation` prompt + model task
types. Active questions whose expected documents no longer exist are marked
`stale` and excluded (reported in `metrics_summary.stale_questions`), never
scored as zero. Emits `evaluation.run_completed` SSE on finish.

### List Runs

```http
GET /api/evaluation/runs?target_type=library&target_id={id}&question_set_id={id}&limit=20
```

Returns newest-first run summaries with `metrics_summary`:

```json
{
  "question_count": 25, "scored_retrieval_count": 24,
  "found_at_5_rate": 0.84, "found_at_10_rate": 0.92, "mrr": 0.71,
  "judged_count": 25, "passed_count": 21,
  "avg_judge_scores": {"relevance": 0.88, "accuracy": 0.81, "groundedness": 0.9},
  "latency_p50_ms": 420.0, "latency_p95_ms": 880.0, "stale_questions": 1
}
```

### Get Run Detail

```http
GET /api/evaluation/runs/{run_id}
```

Summary plus per-question `results[]`: retrieved docs in rank order,
`retrieval_metrics` (`found_at_5`, `found_at_10`, `best_rank`,
`reciprocal_rank`), and for agent runs the answer text, judge scores, and
judge rationale.

### Re-judge a Partial Run

```http
POST /api/evaluation/runs/{run_id}/rejudge
```

**Response (202).** When the judge model was unavailable mid-run, the run
finishes with status `partial` (retrieval metrics intact, unjudged answers
kept). Rejudge re-scores only the unjudged results; `409` if there is nothing
to re-judge or the run is still in progress.

---

## Events Service

Server-sent events for real-time status updates.

### Subscribe to Events

```
GET /api/events
```

**Response:** `text/event-stream`

**Event Types:**

| Event | Payload | Triggered By |
|-------|---------|-------------|
| `agent.created` | `{"id": "...", ...}` | Agent created |
| `agent.updated` | `{"id": "...", ...}` | Agent updated |
| `agent.deleted` | `{"id": "..."}` | Agent deleted |
| `knowledge.created` | `{"id": "...", ...}` | Source created |
| `knowledge.indexed` | `{"id": "...", ...}` | Source indexed |
| `knowledge.deleted` | `{"id": "..."}` | Source deleted |

**Event Format:**
```
event: agent.created
data: {"type": "agent.created", "payload": {"id": "uuid", ...}, "source": "api", "timestamp": "2024-01-14T10:00:00Z"}
```

### Get Event Status

```
GET /api/events/status
```

Returns current event stream status.

**Response:**
```json
{
  "subscribers": 3
}
```

---

## Config Service

System configuration endpoints.

### Get Embedding Configuration

```
GET /api/config/embedding
```

**Response:**
```json
{
  "provider": "openai",
  "model": "text-embedding-3-small",
  "dimensions": 1536
}
```

---

## Docs Service

### Get API Reference

```
GET /api/docs/api-reference
```

Returns the raw markdown content of this API specification. Used by the frontend API Reference page to render documentation.

**Response:** `text/markdown` - Raw markdown content of `API.md`

---

## Error Responses

All endpoints return consistent error responses:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**HTTP Status Codes:**
| Code | Description |
|------|-------------|
| `400` | Bad Request - Invalid input |
| `404` | Not Found - Resource doesn't exist |
| `413` | Payload Too Large - File exceeds size limit |
| `422` | Unprocessable Entity - Validation error |
| `500` | Internal Server Error - Server-side error |
| `503` | Service Unavailable - External service down |

---

## Rate Limiting

Rate limiting is configured via slowapi. High-cost endpoints (e.g. library chat) carry per-route, per-IP limits. Platform API keys accept a `rate_limit_rpm` field at creation; it is stored but per-key enforcement is not yet wired up (tracked on the roadmap).

---

## Authentication

Requests from localhost and trusted networks are open by default, so a plain local deployment works with no setup. Auth enforcement activates when the instance is exposed externally (`EXTERNAL_HOSTNAME` or `AUTH_TOKEN` configured): external clients must then present a platform API key as a Bearer token. The same rules gate the MCP server at `/mcp`.

### Getting a key

Bootstrap the first admin key (self-disables with `409` once any active key exists). Run it from the host or a trusted network — once auth enforcement is active, external callers can't reach it without credentials:

```bash
curl -X POST http://localhost:8002/api/auth/bootstrap
```

The full key is returned once — store it securely. Additional keys can be created with an admin key via `POST /api/auth/keys` (body: `name`, `scopes`, optional `rate_limit_rpm`, `expires_at`) or in the UI under **Configure → API Keys**. `GET /api/auth/keys` lists keys (hashes never returned); `DELETE /api/auth/keys/{key_id}` soft-revokes.

### Scopes

Keys carry scopes with a hierarchy: `admin` includes `write`, which includes `read`. Mutating REST endpoints and write MCP tools require `write`; key management requires `admin`.

### Using a key

```bash
curl -H "Authorization: Bearer <your-platform-key>" https://your-host/api/agents
```

Note: per-agent query keys are separate from platform keys — they authorize only that agent's query endpoint and are sent as an `X-API-Key` header, not a Bearer token.

---

## OpenAPI / Swagger

Interactive API documentation is available **only when `DEBUG_MODE=true`**:
- Swagger UI: `GET /docs`
- ReDoc: `GET /redoc`
- OpenAPI JSON: `GET /openapi.json`

These endpoints return `404` in production mode.
