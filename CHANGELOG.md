# Changelog

All notable changes to Agentbase are documented here.

## [1.0.0] - 2026-07-05

### BREAKING CHANGES
- **All MCP tool names now carry the `agentbase_` service prefix** (#85).
  Every tool exposed by the MCP server at `/mcp` was renamed from its generic
  name to `agentbase_<name>` — for example `search_sources` is now
  `agentbase_search_sources`, `create_library` is now `agentbase_create_library`,
  and `get_workflow_guide` is now `agentbase_get_workflow_guide`. All 84 tools
  are affected. This follows the MCP `{service}_{action}_{resource}` naming
  best practice and prevents tool-name collisions when clients connect to
  multiple MCP servers. No transition aliases are provided.

  **Client migration:** No server config change is needed — the MCP endpoint
  URL and authentication are unchanged. Connected clients must reconnect
  (start a new MCP session) to pick up the new tool list, then update anything
  that references tools by name: hardcoded tool calls in scripts or agents,
  allowlists/permission rules (e.g. `mcp__<server>__search_sources` becomes
  `mcp__<server>__agentbase_search_sources`), and prompts or skills that
  mention tool names.

## [Unreleased]

### Security
- **Tunnel-proxied requests now require an API key.** Tunnels that terminate
  on the Docker host (e.g. Cloudflare Tunnel, mesh-VPN funnels) deliver
  traffic to the backend from a host-local source IP, which the
  `TRUSTED_NETWORKS` check treated as internal — leaving `/mcp` and the REST
  API open to unauthenticated public requests. `_is_external_request` now
  classifies any request carrying forwarding headers (`X-Forwarded-For`,
  `Forwarded`, `X-Forwarded-Host/Proto`) as external unless the proxy
  authenticated itself via `INTERNAL_FORWARD_SECRET`. Direct localhost/LAN
  clients are unaffected (they never send forwarding headers, and sending
  one can only downgrade trust, so the check cannot be spoofed into access).
  **Migration:** clients connecting through a tunnel must now send
  `Authorization: Bearer <platform-api-key>` — create a key via
  `POST /api/auth/keys` from the local network.
- The MCP connection gate now also covers WebSocket handshakes, which
  previously bypassed the connection-level auth check entirely.
- The MCP 401 rejection log now includes the resolved client IP and
  `X-Forwarded-For` chain for easier debugging.

### Added
- **Sitemap Auto-Discovery**: URL sources now automatically discover sitemaps by checking `robots.txt` and common locations (`/sitemap.xml`, `/sitemap-1.xml`, etc.)
- **Three URL scanning modes**: Auto-Discover (default), Crawl Links, Manual Sitemap
- **Discovered sitemap display**: UI shows the discovered sitemap URL when found
- **Increased page limit**: Sitemap scans now support up to 1000 pages (previously 500)
- **Responsive Design**:
  - Mobile-optimized layout with collapsible sidebar
  - Sheet-based navigation menu for small screens
  - Responsive Chat interface with drawer-based conversation history

### Changed
- URL scanning API response now includes `sitemap_url` field showing which sitemap was used
- Frontend API client updated with `scanWithAutoDiscover()` method
- Default scan mode changed from "Crawl Links" to "Auto-Discover"

---

## [0.2.0] - 2025-01-13

### Added
- **URL-based Knowledge Sources**: 2-stage flow for adding web content
  - Stage 1: Scan URL to discover pages (via sitemap or crawling)
  - Stage 2: Select specific pages to index
- **Web Scraper Service** (`backend/app/services/web_scraper.py`)
  - Playwright-based scraping with Chromium
  - Stealth mode to bypass bot detection
  - Support for both link crawling and sitemap parsing
  - Rate limiting (500ms between requests)
- **Sitemap parsing**: Fetches URLs from sitemap.xml files, supports sitemap index files
- **Path filtering**: Filter sitemap URLs by path substring
- **Tree selection UI**: Expandable tree view for selecting pages to index
- **Batch embedding**: Process embeddings in batches of 50 for efficiency

### Changed
- Knowledge source model now includes `selected_urls` field for URL sources
- Dockerfile updated to include Playwright and Chromium browser
- Browser cache copied to non-root user in Docker image

### Fixed
- Playwright browser not found error for non-root Docker user
- HTTP 403 errors from vendor documentation sites using stealth mode

---

## [0.1.0] - 2025-01-12

### Added
- **Initial project scaffold**
  - FastAPI backend with async SQLAlchemy
  - React 18 frontend with TypeScript and Vite
  - Docker Compose setup with PostgreSQL and Qdrant
  - TailwindCSS styling with dark theme

- **LLM Provider Abstraction Layer**
  - Ollama provider (local models)
  - OpenAI provider (GPT models + embeddings)
  - Anthropic provider (Claude models)
  - Grok provider (xAI models)
  - Health check endpoints for all providers

- **Project Management**
  - Create, read, update, delete projects
  - Project-specific model assignments
  - Conversation organization by project

- **Chat Interface**
  - Real-time chat with AI models
  - Conversation history persistence
  - Task type toggle (Knowledge vs Coding)
  - Markdown rendering with code highlighting
  - Copy code button

- **Knowledge Base (Directory Sources)**
  - Index local directories with .md, .txt, .html, .json files
  - Qdrant vector storage with OpenAI embeddings
  - Semantic search with configurable top-k
  - Collection-per-source isolation

- **Provider Configuration UI**
  - API key management (masked display)
  - Endpoint configuration for Ollama
  - Connection test functionality
  - Model availability display

- **Model Assignment UI**
  - Task-based model routing (knowledge/coding)
  - Global and project-level assignments
  - Embedding model selection

### Infrastructure
- Docker Compose orchestration
- PostgreSQL 15 for metadata storage
- Qdrant integration for vector search
- Health check endpoints
- Structured logging with structlog

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 0.2.0 | 2025-01-13 | URL-based knowledge sources, web scraping |
| 0.1.0 | 2025-01-12 | Initial release with core functionality |
