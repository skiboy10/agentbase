# Agentbase

A self-hosted knowledge curation engine. Curate sources into libraries of deep vertical knowledge, bind them to agents, and measure answer quality — multi-provider LLM support and a full RAG pipeline, exposed via REST API and MCP for integration by external applications.

## Intended Use

Curate knowledge into a RAG repository to create focused, specialized agents. Management UI for configuration and testing. Intended to act as a service layer consumed by other applications and AI agents.

## Features

- **Multi-Provider LLM Support**: Ollama (local), OpenAI, Anthropic, Grok, Google
- **RAG Pipeline**: Index content from URLs, PDFs, local directories, YouTube transcripts, and file uploads
- **Libraries**: Curate indexed sources into focused collections that agents search
- **Taxonomy Classification**: Auto-classify content with LLM enrichment; coverage and gap analysis
- **Agent Management**: Create agents with API keys and library bindings
- **Prompt Studio**: Version-controlled system prompts with RAG context templates
- **Evaluation & Experiments**: Golden question sets, LLM-judged scorecards, and A/B testing of agent configurations with baseline comparison and one-click promotion
- **Source Freshness**: Directory watchers and refresh policies keep indexed content current
- **MCP Server**: 84 tools for AI agent access (Claude Code, etc.)

## Interface Options

Agentbase is designed for flexibility with multiple access patterns:

| Interface | Audience | Status |
|-----------|----------|--------|
| **Management UI** | Developers, ML Engineers | Available |
| **REST API** | Applications, Integrations | Available |
| **MCP Server** | AI Agents (Claude Code, etc.) | Available |

The **headless REST API** enables embedding Agentbase capabilities into any application without the management UI. All functionality is exposed via REST endpoints for programmatic access.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose                                │
├─────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────────────────────┐  ┌───────────┐ │
│  │   React UI   │  │         FastAPI              │  │ PostgreSQL│ │
│  │   :3002      │◀▶│         :8002                │◀▶│ (metadata)│ │
│  └──────────────┘  │                              │  └───────────┘ │
│                    │  ┌─────────┐ ┌────────────┐  │                │
│  ┌──────────────┐  │  │  Agent  │ │    RAG     │  │  ┌───────────┐ │
│  │  REST API    │◀▶│  │ Service │ │  Service   │  │◀▶│  Qdrant   │ │
│  │  (headless)  │  │  └─────────┘ └────────────┘  │  │ (vectors) │ │
│  └──────────────┘  │  ┌─────────┐ ┌────────────┐  │  └───────────┘ │
│                    │  │Ingestion│ │  Provider  │  │                │
│  ┌──────────────┐  │  │ Service │ │  Gateway   │  │                │
│  │  MCP Server  │◀▶│  └─────────┘ └────────────┘  │                │
│  │  (/mcp)      │  │  ┌─────────┐                │                │
│  └──────────────┘  │  │ Prompt  │                │                │
│                    │  │ Service │                │                │
│                    │  └─────────┘                │                │
│                    └──────────────────────────────┘                │
└─────────────────────────────────────────────────────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │    ./data/ (local)    │
                    │  ├── postgres/        │
                    │  ├── qdrant/          │
                    │  └── uploads/         │
                    └───────────────────────┘
```

### Core Microservices

| Service | Responsibility |
|---------|----------------|
| **RAGService** | Embedding generation, vector search, context retrieval |
| **IngestionService** | Web scraping, document processing, chunking |
| **ProviderGateway** | Multi-LLM abstraction (Ollama, OpenAI, Anthropic, Grok, Google) |
| **PromptService** | Prompt versioning, default resolution, template assembly |
| **AgentService** | Agent CRUD, API key management, knowledge bindings |

## Prerequisites

- **Docker & Docker Compose** (required)
- **At least one LLM provider**:
  - [Ollama](https://ollama.ai) running locally (free, recommended for getting started)
  - OR an API key for OpenAI, Anthropic, or Grok
- **Qdrant** (vector store):
  - Use an existing instance, OR
  - Use the included Qdrant container

## Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/skiboy10/agentbase.git
   cd agentbase
   ```

2. **Copy environment template:**
   ```bash
   cp .env.example .env
   ```

3. **Configure your `.env` file:**

   Generate the required secrets:
   ```bash
   # Paste each value into .env (SECRET_KEY, INTERNAL_FORWARD_SECRET)
   openssl rand -hex 32
   ```

   At minimum, configure one LLM provider:
   ```bash
   # For local Ollama (recommended for getting started)
   OLLAMA_BASE_URL=http://host.docker.internal:11434

   # OR for cloud providers
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   ```

4. **Start the services:**
   ```bash
   # If you have an external Qdrant instance
   docker compose up -d

   # If you need the included Qdrant
   docker compose --profile with-qdrant up -d
   ```

5. **Verify installation:**
   ```bash
   curl http://localhost:8002/health
   ```

6. **Access the UI** at `http://localhost:3002`

7. **Build your first library:** open **Sources**, add a documentation URL, and click **Index**. When indexing finishes, create a **Library**, add the source to it, and try a query on the library's **Retrieval** tab. The in-app **Quickstart** page (left sidebar, under Reference) walks through every step, including binding the library to an agent.

## Connecting AI Agents (MCP)

Agentbase mounts an MCP (Model Context Protocol) server at `http://localhost:8002/mcp` exposing 84 tools (all named `agentbase_*`) — everything in the UI can also be done by an agent: building libraries, searching knowledge, running evaluations and experiments.

**Authentication:** requests from localhost and trusted networks are open by default, so a local agent can connect with no setup. If you expose Agentbase externally (`EXTERNAL_HOSTNAME`/`AUTH_TOKEN` configured), external clients must send a platform API key as a Bearer token. Create the first key with the one-time bootstrap endpoint (it self-disables once any key exists):

```bash
curl -X POST http://localhost:8002/api/auth/bootstrap
# → returns the key once; store it securely
```

Keys can also be managed in the UI under **Configure → API Keys**, with `read` / `write` / `admin` scopes.

**Connect Claude Code:**

```bash
# Local (no auth needed)
claude mcp add --transport http agentbase http://localhost:8002/mcp

# Remote instance with an API key
claude mcp add --transport http agentbase https://your-host/mcp \
  --header "Authorization: Bearer <your-api-key>"
```

**Discover workflows:** once connected, call the `agentbase_get_workflow_guide` tool with no arguments to list step-by-step recipes (build a library from web or files, configure an agent, run evaluations and experiments, taxonomy setup, maintenance), or pass a goal like `"evaluate my agent"` to get the matching recipe.

## Data Persistence

All data is stored in the `./data/` directory on your local filesystem:

```
./data/
├── postgres/    # PostgreSQL database files
├── qdrant/      # Vector store data (if using included Qdrant)
└── uploads/     # Uploaded PDF files
```

This directory is created automatically on first run. Your data survives container rebuilds.

**To backup:** Simply copy the `./data/` directory.

**To reset:** Stop containers and delete `./data/`.

## Configuration

### LLM Providers

Configure providers via environment variables or the admin dashboard:

| Provider | Environment Variable | Notes |
|----------|---------------------|-------|
| Ollama | `OLLAMA_BASE_URL` | Default: `http://host.docker.internal:11434` |
| OpenAI | `OPENAI_API_KEY` | GPT models + embeddings |
| Anthropic | `ANTHROPIC_API_KEY` | Claude models |
| Grok | `GROK_API_KEY` | xAI models |
| Google | `GOOGLE_API_KEY` | Gemini models |

### Embeddings

For RAG to work, you need an embedding provider:

```bash
EMBEDDING_PROVIDER=openai          # or ollama
EMBEDDING_MODEL=text-embedding-3-small
```

### Ports

Default ports (configurable in `.env`):

| Service | Port |
|---------|------|
| Frontend | 3002 |
| Backend API | 8002 |
| PostgreSQL | 5434 |
| Qdrant (if included) | 6335 |

## Project Structure

```
agentbase/
├── backend/
│   └── app/
│       ├── api/          # FastAPI routes
│       ├── core/         # Config, database
│       ├── models/       # SQLAlchemy models
│       ├── providers/    # LLM provider implementations
│       └── services/     # Business logic (RAG, ingestion, agents)
├── frontend/
│   └── src/
│       ├── pages/        # React page components
│       ├── components/   # Shared UI components
│       ├── contexts/     # React contexts
│       └── services/     # API client
├── data/                 # Persistent data (gitignored)
├── docker/               # Dockerfiles
├── docker-compose.yml
└── .env.example
```

## Development

All development uses Docker. Backend auto-reloads via volume mount; frontend requires a rebuild.

```bash
# Rebuild frontend after changes
docker compose build frontend && docker compose up -d frontend

# Backend auto-reloads — just save and check logs
docker compose logs -f backend

# Run tests
docker compose exec backend pytest tests/ -x --tb=short
```

## Documentation

| Document | Contents |
|----------|----------|
| [QUICKSTART.md](./QUICKSTART.md) | User guide - what each tab does |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Reference architecture, design principles, service interfaces |
| [BACKLOG.md](./BACKLOG.md) | Design specs and grooming notes (GitHub Issues is the live backlog) |
| [API.md](./API.md) | REST API specification with examples |
| [CLAUDE.md](./CLAUDE.md) | Codebase documentation for AI assistants |

## Troubleshooting

### Ollama not connecting

On **macOS/Windows**, Docker uses `host.docker.internal` to reach the host machine. Ensure Ollama is running:
```bash
ollama serve
```

On **Linux**, you may need to use your host IP or configure Docker networking:
```bash
OLLAMA_BASE_URL=http://172.17.0.1:11434
```

### Database connection issues

Check that PostgreSQL is healthy:
```bash
docker compose ps
docker compose logs postgres
```

### Permission issues with ./data/

On Linux, you may need to set permissions:
```bash
sudo chown -R 1000:1000 ./data
```

## License

Apache 2.0 — see [LICENSE](./LICENSE).
