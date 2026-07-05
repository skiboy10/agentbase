# Agentbase - Product Backlog

**The live backlog is [GitHub Issues](https://github.com/skiboy10/agentbase/issues).** This file holds the project vision and serves as a staging area for design specs while they're being groomed — once a spec is ready, it becomes an issue and is removed from here.

## Project Vision

Agentbase exists to curate and supply deep vertical knowledge so that agents can provide accurate answers to complex problems in specialized domains. It is an open source knowledge curation engine providing core microservices for knowledge ingestion, RAG, and agent configuration, exposed via REST API and MCP for integration by external applications.

### Target Users
1. **Developers** - Build and configure agents with curated knowledge via API
2. **ML Engineers** - Experiment with retrieval and embedding strategies
3. **AI Agents** - Programmatic access via REST API or MCP
4. **External Applications** - Consume knowledge and agent capabilities headlessly

---

## Related Documentation

| Document | Contents |
|----------|----------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Reference architecture, design principles, entity relationships, service interfaces |
| [API.md](./API.md) | REST API specification with request/response examples |
| [CLAUDE.md](./CLAUDE.md) | Project structure, tech stack, code style guidelines |
| [docs/evaluation-experiments-design.md](./docs/evaluation-experiments-design.md) | Approved design for the evaluation & experiments system (index experiments pending) |

---

## Open Roadmap

Tracked as GitHub Issues (labeled `public-roadmap`); titles listed here for orientation. See each issue for the full spec and discussion.

### Features
- **Agent Query page** — chat-style conversation interface for agents
- **Agentic knowledge curation** — auto-discover sources and build collections
- **Cross-library source sharing, Stage 2** — UI + embedding-lock enforcement on top of the shipped many-to-many schema
- **Provenance metadata schema** — required fields on ingest for knowledge sources
- **Default classifier model assignment** — design + implementation
- **Store indexed chunks in PostgreSQL** — for auditing and comparison alongside Qdrant

### Platform & Security Hardening
- **Enforce per-key `rate_limit_rpm`** on platform API keys (stored today, not enforced)
- **MCP auth hardening** — fail-closed `check_mcp_scope`, per-route scope lint
- **MCP tool edge cases** — error paths, pagination clamps, lazy-load review

### Code Health
- **Migrate hand-rolled forms** to react-hook-form + zod + shadcn Form

### Distribution
- **Helm chart, SDKs, documentation site**

---

## Design Staging

No specs currently in grooming. New feature designs land here for iteration before being cut into issues.
