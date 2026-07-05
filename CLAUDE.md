# Agentbase

Open source knowledge curation engine. Curate + supply deep vertical knowledge so agents give accurate answers to complex specialized-domain problems. Multi-provider LLM, RAG pipeline, exposed via REST API and MCP.

**Agentbase is standalone service layer with own repository.**

## Documentation

| Document | Contents |
|----------|----------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | Reference architecture, design principles, entity relationships |
| [API.md](./API.md) | REST API spec with examples |
| [BACKLOG.md](./BACKLOG.md) | Design specs + grooming notes (GitHub Issues is live backlog) |

### Documentation Maintenance

**Keep docs in sync with changes:**

- **Design/architecture changes** → Update ARCHITECTURE.md
- **API endpoint changes** → Update API.md
- **New features/roadmap** → Create GitHub Issue (BACKLOG.md is grooming/design only)
- **Before committing** → Review CLAUDE.md and MEMORY.md for stale content. Update factual claims (model counts, route lists, nav items, tool counts) affected by changes. Prune completed items, fix broken refs, remove outdated notes. These files = primary context for future sessions — stale entries cause drift + wasted work.

### Documentation Governance

- **DRY hierarchy:** Each CLAUDE.md has only scope-unique content. Shared rules at highest tier.
- **Recipe pattern:** Code examples >10 lines go in `docs/recipes/`, summary + link in CLAUDE.md.
- **Archive discipline:** Dev screenshots → `.archive/screenshots/` after verification.
- **docs/ for active refs:** Completed test plans/results → `.archive/docs/`.
- **No duplicates:** Reference links only, never copy between files.

## Backlog Management

**GitHub Issues** = single source of truth for backlog. `BACKLOG.md` = design/grooming staging — specs live there until issues created.

- **Setup:** `bash docs/backlog-setup/setup-github-backlog.sh` (labels, milestones, seed issues)
- **Agent guide:** `docs/backlog-setup/AGENT_GUIDE.md` — `gh` CLI patterns for issues
- **Labels:** Every issue needs one each: `type:`, `area:`, `priority:`
- **Milestones:** Security Hardening, Code Health, RAG Pipeline, Knowledge Lifecycle, Platform Features, Distribution & Scale, Active Sprint

**Agent behavior on backlog items:**
1. Before starting → comment on issue, add assignee
2. During work → comment if scope changes or blockers
3. On completion → comment with summary + commit ref, close issue
4. New work discovered → create new issue, reference parent (`Relates to #42`)

## Agent Directives

1. **Research first:** New features start with research. Verify logic doesn't duplicate existing `providers/`.
2. **Working documents:** Planning artifacts + notes go in `/docs/`.
3. **Docker environment:** All commands run in Docker (Ports: 3002, 8002, 5434).
4. **Dependencies:** Update `requirements.txt` + rebuild backend container for new packages.
5. **Verification:** Run `pytest` after backend changes. Verify UI matches shadcn/ui.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | FastAPI, SQLAlchemy (async), Python 3.11 |
| Frontend | React 18, TypeScript, Vite, TailwindCSS |
| Database | PostgreSQL 15 |
| Vector Store | Qdrant |
| Web Scraping | Playwright (Chromium) |
| Containers | Docker Compose |

**Ports:** Frontend 3002, Backend 8002, PostgreSQL 5434

## Project Structure

```
backend/app/
├── api/              # FastAPI routers (modular: agents/, sources/, library.py)
├── core/             # Config, database
├── models/           # SQLAlchemy models
├── providers/        # LLM implementations (ollama, openai, anthropic, grok, google)
└── services/         # Business logic (modular: ingestion/, rag/, library/, web_scraper/, library_chat.py)

frontend/src/
├── pages/            # Sources, Automations, Libraries, LibraryDetail, Taxonomy, TaxonomyDetail, Agents, AgentQuery, PromptStudio, Providers, Settings, APIKeys, Quickstart, APIReference, Experiments
├── components/       # Modular components (agents/, sources/, libraries/)
└── services/api/     # Modular API client with types/
```

## Modular Architecture

Backend services/routers: facade + sub-modules with barrel exports (`__init__.py`).
Frontend components: tabs/hooks/stages with `index.ts` barrel exports.

See ARCHITECTURE.md for patterns + file size guidelines.

## Database Models

`/backend/app/models/models.py` (Phase 3 rename complete — classes + tables now use Source/Library naming):
- `Project`, `ProjectSource` - Project org (deprecated — #56, DB tables remain; `ProjectAgent` + `agents.project_id` dropped in #123)
- `Source`, `IndexingLog`, `DocumentContent` - RAG pipeline (tables: `sources`, `indexing_logs`, `document_content`)
- `Library`, `LibrarySource`, `Document` - Library entity, source bindings, docs (tables: `libraries`, `library_sources`, `documents`)
- `Agent`, `AgentSource`, `AgentLibrary` - Agent config + source-level and library-level bindings
- `WatcherEvent` - Directory-watcher event log
- `Taxonomy`, `TaxonomyTerm`, `TaxonomySuggestion` - Classification
- `ProviderConfig`, `ModelAssignment` - LLM config
- `Prompt` - System prompts per task type
- `APIKey` - Platform API keys (Argon2id hashed)
- `Job` - Background job queue (index, re-enrich, retry)
- `Experiment` - Library-centered experiments (table: `experiments`); pipeline type (agent config overrides) live, index type (shadow re-index) is Slice 4 — see docs/evaluation-experiments-design.md
- `SourceMetadataSchema` - Metadata field definitions
- `QuestionSet`, `Question`, `EvalRun`, `EvalResult` - Evaluation framework (library-owned golden question sets, scorecards; tables: `question_sets`, `questions`, `eval_runs`, `eval_results`)

## API Routes (Core)

```
/api/projects      - CRUD, source assignments, /default-model (deprecated — #56)
/api/providers     - Config, test, list models
/api/sources       - Sources CRUD, /scan-url, /search, /deep-search, /{id}/index, /refresh, /{id}/re-enrich
/api/sources       - /watchers/status, /watchers/{id}/start|stop|sync
/api/sources       - /analytics (system-wide stats), /stale (freshness status)
/api/libraries     - CRUD, source bindings, document CRUD, /recalculate-stats, /{id}/coverage, /{id}/chat
/api/taxonomies    - CRUD, terms, /coverage, /stale, /suggestions
/api/prompts       - CRUD, /default, /{id}/duplicate
/api/agents        - CRUD, API keys, duplicate, /libraries bindings
/api/experiments   - Library-scoped pipeline experiments: CRUD, /compare, /comparison, /promote
/api/evaluation    - Question sets CRUD, questions, /generate (LLM drafting job), /runs (scorecards), /runs/{id}/rejudge
/api/events        - SSE subscription, /status
/api/config        - Embedding configuration
/api/docs          - API reference (serves API.md)
/api/jobs          - Background job queue status
/api/metadata      - Metadata schema management
/api/auth          - API key management (create, list, revoke, bootstrap)
/mcp               - MCP server (84 tools, all prefixed agentbase_*, across auth, projects, agents, libraries, sources, source_ops, sources_docs, sources_upload, taxonomy, evaluation, guide, discovery)
```

See [API.md](./API.md) for complete spec.

## Frontend API Client

```typescript
// Modular imports (preferred)
import { agentsApi } from '../services/api/agents';
import type { Agent } from '../services/api/types/agents';

// Backward compatible barrel import
import { agentsApi, Agent } from '../services/api';
```

**Namespaces:** `sourcesApi`, `libraryApi`, `providersApi`, `promptsApi`, `agentsApi`

## Agent Development Assets

Runtime config (prompts, temperature, library bindings, API keys) in **Postgres** (`agents`, `agent_sources`, `agent_libraries` tables). Dev artifacts at `~/agentbase-data/agent-dev/`.

```
~/agentbase-data/agent-dev/
├── README.md                        # What goes here vs. postgres
├── agents/{agent-slug}/
│   ├── prompt.md                    # Current prompt snapshot + version history
│   ├── test-log.md                  # Test findings, tuning session notes
│   └── notes.md                     # Model-specific notes (fine-tune, quantization)
└── test-scripts/
    └── {test-name}.sh               # Reusable curl test scripts
```

**When to write here:**
- After prompt tuning → snapshot prompt + findings to `agents/{slug}/prompt.md` and `test-log.md`
- Creating/modifying agents → document model notes (temperature, context limits, RAG sensitivity)
- Building test harnesses → save curl scripts to `test-scripts/`

**Key principles:**
- Postgres = runtime source of truth; these files = dev reference
- Each agent gets directory named by slug (`agent_id` field)
- `prompt.md` version history tracks what changed + why
- Test logs capture what worked, failed, + root cause

## Data Isolation

Prevent accidental commits of data files to the public repo:

**External Data Directory:**
```bash
# Setup (one-time)
mkdir -p ~/agentbase-data/{postgres,qdrant,uploads,agent-dev}

# Create docker-compose.override.yml (gitignored) to redirect volumes
# See existing docker-compose.override.yml for example
```

**Pre-commit Hooks:**
```bash
./scripts/setup-git-hooks.sh   # Enable hooks
git commit --no-verify          # Bypass (not recommended)
```

Hooks block: data files (.db, .sqlite, credentials), .env, large files (>10MB).

**Release Verification:**
```bash
./scripts/verify-release.sh    # Test clean clone works
./scripts/verify-release.sh --keep  # Keep test dir for inspection
```

**Public Release:**
```bash
./scripts/release-to-public.sh          # Push to public repo
./scripts/release-to-public.sh v1.0.0   # Push with version tag
```

Repo: `skiboy10/agentbase` (public — the primary development repo since v1)

## Development Environment

**Docker-only dev.** Remote access (e.g., `192.168.x.x:3002`):
- Frontend changes: `docker compose build frontend && docker compose up -d frontend`
- Backend changes: Auto-reload via volume mount (no rebuild)
- Never use Vite dev server (localhost-only)

```bash
docker compose up -d                    # Start
docker compose build frontend           # Rebuild frontend
docker compose logs -f backend          # Logs
curl http://localhost:8002/health       # Health check
```

**macOS keychain unlock:** If builds fail "keychain cannot be accessed":
```bash
security -v unlock-keychain ~/Library/Keychains/login.keychain-db
```

**Git worktrees for branch work.** The running Docker stack volume-mounts the main
working copy and auto-runs `alembic upgrade head` on startup. Switching branches
*in that checkout* shifts files under the live app and can leave the DB ahead of the
code — once a `--reload` + failed-migration combo caused a silent multi-hour MCP
outage (startup now tolerates a DB ahead of code, but the workflow rule still holds).

Keep the main checkout on its stable branch (the one the stack runs); do feature/fix
work in a **worktree** instead:
```bash
git worktree add ../agentbase-<branch> -b <branch>   # new branch in a sibling folder
git worktree list                                    # see all worktrees
git worktree remove ../agentbase-<branch>            # clean up when merged
```
Worktrees are for editing/committing. The `docker-compose.override.yml` (data paths,
mounts) is gitignored and lives only in the main checkout, so run the stack from the
main checkout — bring worktree changes into the live app by merging, not by `checkout`.

## Testing

```bash
# Backend (after any backend/app/ changes)
docker compose exec backend pytest tests/ -x --tb=short

# Frontend (production container - verify build)
docker compose build frontend
```

## Code Style

- **Backend:** Type hints, async/await, Pydantic models
- **Frontend:** TypeScript strict, functional components, hooks
- No emojis unless requested

## Examples & placeholder hygiene

Agentbase is open source and read by external users, customers, and agents (via MCP). Helper text, placeholders, example payloads, code comments, docstrings, test fixtures, and documentation **must not reference real clients, partners, vendors, or individuals**.

- Use `ACME` (or `ACME Q4 Plan`, `ACME Corp`, etc.) as the canonical generic client name in placeholders, examples, and tests.
- Use `Jane Doe` / `John Doe` for example individuals when needed.
- Use generic product names (`Product Documentation`, `Sales Playbook`) when describing specific content types.
- This applies to: `placeholder=`, `e.g., ...` strings, JSON examples in API.md, MCP guide tool examples, docstring `Example::` blocks, test fixture paths (`/tmp/<client>` → `/tmp/acme`), and any helper/tooltip copy.
- **Real client data in a user's local instance is fine** — this rule governs the *source code and docs* that ship in the repo, not the runtime database content the user indexes themselves.

If you're unsure whether a name in code is real-vs-fictional, treat it as real and replace.

## Agentic Design Principles

Files small enough for AI agents to understand + modify safely.

| Type | Target | Hard Limit |
|------|--------|------------|
| Backend Service | 300-500 | 800 lines |
| Backend Router | 200-400 | 600 lines |
| Frontend Page | 200-400 | 600 lines |
| Frontend Component | 100-200 | 400 lines |

**Splitting Pattern:** Create same-name directory → barrel export (`__init__.py`/`index.ts`) → split into focused modules → `README.md` with module mission.

## Agent Teams

Predefined team patterns for parallel dev. Use when task splits across independent layers. See `.claude/plans/peaceful-toasting-fairy.md` for full strategy + prompts.

### Team Patterns

| Pattern | Teammates | When to Use |
|---------|-----------|-------------|
| **Full-Stack Builder** | Backend + Frontend + QA | Feature spanning backend + frontend |
| **Code Review** | Security + Architecture + Integration | Before merging big PRs |
| **Hypothesis Debugger** | Backend + Frontend + Infra investigators | Cross-layer bugs, unclear root cause |
| **Docs Sync** | Refactor + Docs + Test | Large refactors affecting architecture |

### File Ownership (prevent conflicts)

| Teammate | Owns | Never Touches |
|----------|------|---------------|
| Backend | `backend/` — models, schemas, services, api, migrations | `frontend/` |
| Frontend | `frontend/` — types, services/api, hooks, components, pages | `backend/` |
| QA | Docker commands, test execution, Playwright | Source files |

### Teammate Guidelines

- **Sonnet** for implementation, **Haiku** for repetitive tasks, **Opus** for complex leads
- Backend messages frontend directly when API schema finalized
- Require **plan approval** before implementation (lead reviews)
- GPT 5+ models: always temperature 1

## Design System

- **Components:** shadcn/ui + Radix UI primitives
- **Styling:** TailwindCSS, dark/light themes via CSS variables
- **Typography:** Avoid generic fonts (Inter, Roboto, Arial)

## UI Interaction Patterns

### Multi-Select Lists

All multi-select lists support click, shift+click range, select-all. See [docs/recipes/multi-select-lists.md](docs/recipes/multi-select-lists.md).

### Filter State Persistence

URL search params = single source of truth for filter state. See [docs/recipes/url-filter-persistence.md](docs/recipes/url-filter-persistence.md).

### Notifications (one rule)

- **Transient action outcome** (save/delete/copy success, mutation error) → **toast** (`useToast`).
- **Field validation** → **inline** via shadcn `FormMessage`.
- **Persistent page-load failure** → **`ErrorBanner`** (stays on screen, offers retry).

### Design Tokens (no hardcoded palette colors)

Colors resolve through CSS tokens (`index.css` → `tailwind.config.js`), never raw Tailwind palette (`bg-blue-900`, `text-green-600`). Status/score → `--status-*`; source-type chips → `src/lib/sourceType.ts`; document file-type badges → `src/lib/fileType.ts`.

## UI Navigation

All pages global (no project-scoped sidebar filtering). Sidebar groups: **Knowledge** (Sources, Automations, Libraries, Taxonomy), **Agents** (Agents, Prompt Studio), **Lab** (Experiments), **Configure** (Providers, Settings, API Keys), **Reference** (Quickstart, API Reference).

| Page | Nav group | Description |
|------|-----------|-------------|
| Sources | Knowledge | Source management, indexing, Search Test tab |
| Automations | Knowledge | Per-source watcher/freshness automation control panel |
| Libraries | Knowledge | Curated source collections, document management, retrieval lab, chat |
| Taxonomy | Knowledge | Classification systems, terms, coverage, suggestions, pipeline health (detail page) |
| Agents | Agents | Agent CRUD, library bindings |
| Prompt Studio | Agents | System prompt editing per task type (routed `/prompt-studio`, #58 resolved) |
| Providers | Configure | LLM provider config, model testing |
| Settings | Configure | System configuration |
| API Keys | Configure | Platform API key management |
| Quickstart | Reference | Object reference + getting started |
| API Reference | Reference | Interactive API docs |
| Experiments | Lab | Evaluation workbench: question sets, scorecards, and pipeline experiments (compare/promote) live; index experiments land in Slice 4 (docs/evaluation-experiments-design.md) |

## Knowledge Librarian Skill

`.claude/skills/knowledge-librarian/` — Claude Code skill for autonomous domain library building. Invoke when asked to "build a knowledge library" or "curate knowledge for [topic]". Covers: source discovery, library creation, taxonomy design, coverage gap analysis, maintenance. Recipes in `recipes/` subdirectory.

**Freshness lifecycle fields** on Source model: `freshness_policy` (none/automatic/manual), `stale_after_days`, `refresh_interval_days`, `next_refresh_at`. Background scheduler auto-refreshes `automatic` sources.

## In-Flight Decisions

- **Rename:** Knowledge → Sources, Knowledge Bases → Libraries (#55 — DONE incl. Phase 3 DB class + table rename)
- **Deprecate:** Projects UI removed (#56 — DONE, backend routes + DB tables remain)
- **Future:** Workspaces for multi-tenant isolation (#57, low priority)