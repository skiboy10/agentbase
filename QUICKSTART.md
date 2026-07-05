# Agentbase - Quick Start Guide

A quick reference for each section of the Agentbase interface. The in-app **Quickstart** page (sidebar → Reference) covers the same ground interactively.

---

## Sources (Knowledge)

**Purpose:** Manage data ingestion — where raw content comes from.

- **Add Sources:** URLs (with sitemap crawling), PDFs, local directories, YouTube transcripts, file uploads
- **Index:** Extract text, chunk, and embed into Qdrant
- **Refresh:** Re-crawl URLs to pick up new or updated pages
- **Re-enrich:** Re-classify chunks against a taxonomy (preserves embeddings)
- **Search Test:** Test retrieval quality with sample queries
- **Sub-sources:** Filtered views over a directory root — scope an agent to one subfolder without re-indexing

---

## Automations (Knowledge)

**Purpose:** Keep indexed content current, automatically.

- Directory watchers detect file changes and re-index on the fly
- Freshness policies (`automatic` / `manual`) flag stale sources and schedule refreshes
- Per-source control panel for watcher status, sync, and event history

---

## Libraries (Knowledge)

**Purpose:** Curate sources into searchable collections.

- Group multiple sources into a single searchable unit
- One query searches across all sources in the library
- Stats (documents, chunks) roll up to this level
- Bind libraries to agents for RAG retrieval
- Per-library document management, retrieval lab, and chat

---

## Taxonomy (Knowledge)

**Purpose:** Classification systems for enriching documents.

- Create taxonomies with terms organized by facet (e.g. platform, product, doc category)
- Enrichment classifies each chunk against taxonomy terms via LLM
- View coverage analytics and stale term detection
- Review and approve AI-suggested new terms

---

## Agents

**Purpose:** Create LLM-powered endpoints with knowledge bindings.

- Configure system prompts, model selection, temperature, retrieval depth
- Bind libraries (preferred) or individual sources for automatic RAG retrieval
- Generate API keys for external access
- Query agents directly from the UI

---

## Prompt Studio (Agents)

**Purpose:** Manage the system prompts Agentbase itself uses per task type (enrichment, judging, generation), with versioning.

---

## Experiments (Lab)

**Purpose:** Measure answer quality and A/B test agent configurations.

- **Question Sets:** golden questions per library — write them by hand or draft with an LLM
- **Scorecards:** score retrieval (found@k, MRR) or full agent answers (LLM judge: relevance, accuracy, groundedness)
- **Experiments:** clone an agent's config with overrides (temperature, top-k, model, prompt), compare against the baseline per question, and promote the winner into the live agent

---

## Providers (Configure)

**Purpose:** Configure LLM providers and API keys.

- **Ollama** - Local models (free, private)
- **OpenAI** - GPT models
- **Anthropic** - Claude models
- **Grok** - xAI models
- **Google** - Gemini models

Test connectivity and view available models for each provider.

---

## Settings & API Keys (Configure)

- **Settings:** theme, sidebar preferences, backend configuration display
- **API Keys:** platform keys (scoped `read` / `write` / `admin`) for REST and MCP access — see the README's "Connecting AI Agents" section

---

## Typical Workflow

1. **Configure a Provider** — connect at least one LLM
2. **Create Sources** — point to files, URLs, or directories
3. **Index Sources** — extract text, chunk, and embed into vectors
4. **Create a Library** — group sources into a searchable collection
5. **Create an Agent** — pick a model, write a prompt, bind the library
6. **Query the Agent** — ask questions; RAG context is injected automatically
7. **Evaluate** — build a question set, run a scorecard, and tune with experiments
