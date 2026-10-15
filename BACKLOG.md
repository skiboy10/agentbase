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
| [docs/qdrant-mcp-security-analysis-2026-10.md](./docs/qdrant-mcp-security-analysis-2026-10.md) | 2026-10 analysis: Qdrant optimality, MCP readiness, security review |

---

## Active Sprint focus (groomed 2026-10)

Priority order recommended after the Qdrant / MCP / security review:

1. **Bugs blocking taxonomy/coverage correctness** — #20 (URL/YouTube enrichment), #21 (PATCH term sort_order), #26 (re-enrich → DocumentContent)
2. **Security Hardening** — #10 (enforce `rate_limit_rpm`); refuse insecure `SECRET_KEY` when exposed; pin Qdrant image
3. **RAG Pipeline** — re-enable native Qdrant hybrid fusion; sparse BM25; text-index stemming/stopwords
4. **Knowledge Lifecycle** — #6 provenance schema; #7 classifier model assignment (needs design)
5. **Platform** — #3 Agent Query chat UI; re-scope #4 around in-product automation vs Knowledge Librarian skill

Milestones exist on GitHub (`Security Hardening`, `Code Health`, `RAG Pipeline`, `Knowledge Lifecycle`, `Platform Features`, `Distribution & Scale`, `Active Sprint`) and should stay attached to every open issue.

---

## Open Roadmap

Tracked as GitHub Issues (labeled `public-roadmap`); titles listed here for orientation. See each issue for the full spec and discussion.

### Features
- **Agent Query page** — chat-style conversation interface (#3; still single-shot in UI)
- **Agentic knowledge curation** — in-product automation (#4); **external agent path already exists** via `.claude/skills/knowledge-librarian/` + MCP
- **Provenance metadata schema** — required fields on ingest (#6)
- **Default classifier model assignment** — design + implementation (#7)
- **Store indexed chunks in PostgreSQL** — for auditing and comparison alongside Qdrant (#1)

### Platform & Security Hardening
- **Enforce per-key `rate_limit_rpm`** on platform API keys (#10)
- **Pin Qdrant version + optional API key** for Compose deployments (see analysis)
- **Refuse boot with insecure SECRET_KEY when EXTERNAL_HOSTNAME is set** (see analysis)

### RAG / Qdrant
- **Enable native Prefetch/FusionQuery hybrid + sparse BM25** (#33)
- **Pin Qdrant image + consolidate client + `_qdrant_version` fix** (#34)

### Code Health
- **Migrate hand-rolled forms** to react-hook-form + zod + shadcn Form (#8)
- **Consolidate duplicate `get_qdrant_client` singletons** (bundled in #34)

### Distribution
- **Helm chart, SDKs, documentation site** (#2)

### Open bugs
- #20 URL/YouTube skip enrichment · #21 taxonomy term PATCH · #26 re-enrich DocumentContent backfill

### Security (new)
- **Refuse insecure SECRET_KEY when EXTERNAL_HOSTNAME set** (#35)
- **Re-scope #4 vs Knowledge Librarian skill** (#36)

---

## Design Staging

No specs currently in grooming. New feature designs land here for iteration before being cut into issues.
