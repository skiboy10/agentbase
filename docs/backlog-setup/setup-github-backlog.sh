#!/usr/bin/env bash
#
# setup-github-backlog.sh
# Initializes GitHub Issues labels, milestones, and seed issues
# for the Agentbase backlog.
#
# Prerequisites:
#   - gh CLI installed and authenticated (https://cli.github.com)
#   - You have admin/write access to skiboy10/agentbase
#
# Usage:
#   cd agentbase
#   bash docs/backlog-setup/setup-github-backlog.sh
#
# Note: Uses two-step heredoc pattern (variable assignment then --body "$var")
# because macOS ships bash 3.2, which has a known bug parsing heredocs
# inside $(command substitution). Do NOT refactor back to --body "$(cat <<'EOF'...)".
#
set -euo pipefail

REPO="skiboy10/agentbase"

echo "=== Agentbase — GitHub Backlog Setup ==="
echo "Repository: $REPO"
echo ""

# ──────────────────────────────────────────────
# 1. LABELS
# ──────────────────────────────────────────────
echo "── Creating labels ──"

# Delete GitHub default labels that we won't use
for label in "good first issue" "help wanted" "invalid" "question" "wontfix"; do
  gh label delete "$label" --repo "$REPO" --yes 2>/dev/null || true
done

# Type labels (what kind of work)
gh label create "type: feature"       --color "0E8A16" --description "New capability or user-facing functionality"         --repo "$REPO" --force
gh label create "type: enhancement"   --color "84B6EB" --description "Improvement to existing functionality"               --repo "$REPO" --force
gh label create "type: bug"           --color "D93F0B" --description "Something is broken"                                 --repo "$REPO" --force
gh label create "type: tech-debt"     --color "FEF2C0" --description "Refactoring, cleanup, or architectural improvement"  --repo "$REPO" --force
gh label create "type: docs"          --color "0075CA" --description "Documentation only"                                  --repo "$REPO" --force
gh label create "type: infra"         --color "D4C5F9" --description "CI/CD, deployment, tooling, environments"            --repo "$REPO" --force

# Area labels (which part of the system)
gh label create "area: backend"       --color "E4E669" --description "Backend (FastAPI, services, models)"                 --repo "$REPO" --force
gh label create "area: frontend"      --color "FBCA04" --description "Frontend (React UI)"                                 --repo "$REPO" --force
gh label create "area: rag"           --color "BFD4F2" --description "RAG pipeline (search, chunking, embeddings)"         --repo "$REPO" --force
gh label create "area: knowledge"     --color "C2E0C6" --description "Knowledge sources, ingestion, indexing"              --repo "$REPO" --force
gh label create "area: agents"        --color "F9D0C4" --description "Agent configuration, invocation, API keys"           --repo "$REPO" --force
gh label create "area: mcp"           --color "BFDADC" --description "MCP server and tools"                                --repo "$REPO" --force
gh label create "area: providers"     --color "D4C5F9" --description "LLM provider configuration and model management"     --repo "$REPO" --force
gh label create "area: infra"         --color "C5DEF5" --description "Docker, deployment, CI/CD, environments"             --repo "$REPO" --force
gh label create "area: api"           --color "0075CA" --description "REST API endpoints and middleware"                    --repo "$REPO" --force

# Priority labels
gh label create "priority: critical"  --color "B60205" --description "Blocks other work or active incident"                --repo "$REPO" --force
gh label create "priority: high"      --color "D93F0B" --description "Must do this phase"                                  --repo "$REPO" --force
gh label create "priority: medium"    --color "FBCA04" --description "Should do when capacity allows"                      --repo "$REPO" --force
gh label create "priority: low"       --color "0E8A16" --description "Nice to have, do when convenient"                    --repo "$REPO" --force

# Size labels (t-shirt sizing for estimation)
gh label create "size: S"            --color "EDEDED" --description "< 1 day of work"                                      --repo "$REPO" --force
gh label create "size: M"            --color "D4C5F9" --description "1-3 days of work"                                     --repo "$REPO" --force
gh label create "size: L"            --color "BFD4F2" --description "3-5 days or 1 sprint"                                 --repo "$REPO" --force
gh label create "size: XL"           --color "0075CA" --description "> 1 sprint, consider breaking down"                   --repo "$REPO" --force

# Status labels (for items that need extra state beyond the board column)
gh label create "status: blocked"     --color "B60205" --description "Waiting on external dependency or decision"          --repo "$REPO" --force
gh label create "status: needs-design" --color "D4C5F9" --description "Needs design or specification before implementation" --repo "$REPO" --force
gh label create "status: needs-review" --color "FBCA04" --description "Implementation done, needs review"                  --repo "$REPO" --force

echo ""
echo "Labels created"

# ──────────────────────────────────────────────
# 2. MILESTONES (Roadmap phases)
# ──────────────────────────────────────────────
echo ""
echo "── Creating milestones ──"

gh api repos/$REPO/milestones -f title="Security Hardening" \
  -f description="Security fixes from optimization scan: SSRF, key derivation, path traversal, rate limiting, CORS, auth lint." \
  -f state="open" 2>/dev/null || echo "  (Security Hardening milestone may already exist)"

gh api repos/$REPO/milestones -f title="Code Health" \
  -f description="Backend and frontend code quality improvements from automated scan. Core isolation cleanup, blocking I/O, error handling." \
  -f state="open" 2>/dev/null || echo "  (Code Health milestone may already exist)"

gh api repos/$REPO/milestones -f title="RAG Pipeline" \
  -f description="RAG optimization: multi-source parallel search, hybrid default, taxonomy tags, chunk storage, re-ranking." \
  -f state="open" 2>/dev/null || echo "  (RAG Pipeline milestone may already exist)"

gh api repos/$REPO/milestones -f title="Knowledge Lifecycle" \
  -f description="Freshness tracking, scheduled re-indexing, change detection, staleness alerts, archive/retire actions." \
  -f state="open" 2>/dev/null || echo "  (Knowledge Lifecycle milestone may already exist)"

gh api repos/$REPO/milestones -f title="Platform Features" \
  -f description="New capabilities: expanded file formats, API reference UI, advanced retrieval, dev/prod management." \
  -f state="open" 2>/dev/null || echo "  (Platform Features milestone may already exist)"

gh api repos/$REPO/milestones -f title="Distribution & Scale" \
  -f description="Helm chart, SDKs, documentation site, multi-tenancy, OAuth2/OIDC." \
  -f state="open" 2>/dev/null || echo "  (Distribution & Scale milestone may already exist)"

gh api repos/$REPO/milestones -f title="Active Sprint" \
  -f description="Current sprint work — quick fixes, polish, and in-progress items." \
  -f state="open" 2>/dev/null || echo "  (Active Sprint milestone may already exist)"

echo "Milestones created"

# ──────────────────────────────────────────────
# 3. GITHUB PROJECT (v2)
# ──────────────────────────────────────────────
echo ""
echo "── Creating GitHub Project board ──"
echo ""
echo "NOTE: GitHub Projects v2 creation via CLI requires the project to be"
echo "created under your user account (not the repo). Run this manually:"
echo ""
echo "  gh project create --owner skiboy10 --title 'Agentbase'"
echo ""
echo "Then configure these views in the GitHub UI:"
echo ""
echo "  Board view (default):"
echo "    Columns: Backlog | Ready | In Progress | In Review | Done"
echo ""
echo "  Table view -- 'By Milestone':"
echo "    Group by: Milestone"
echo "    Sort by: Priority label"
echo ""
echo "  Table view -- 'By Area':"
echo "    Group by: Area label"
echo "    Sort by: Priority label"
echo ""
echo "Link the project to the repo at:"
echo "  https://github.com/$REPO/settings -> Projects"
echo ""

# ──────────────────────────────────────────────
# 4. SEED ISSUES
# ──────────────────────────────────────────────
echo "── Creating seed issues ──"
echo ""

# --- Security Hardening ---

body=$(cat <<'EOF'
## Problem
Several security items remain from the optimization scan. SSRF URL validation is missing — scraper endpoints accept arbitrary URLs including internal IPs, localhost, and cloud metadata endpoints.

## Acceptance Criteria
- [ ] Add blocklist for internal IPs, `localhost`, cloud metadata endpoints before scraping
- [ ] Validation applied in `indexers/url.py`, `api/knowledge/operations.py`, `web_scraper/scraper.py`
- [ ] Unit tests for blocked URLs

## Context
From Code Health scan Phase 1 — Security Hardening.
EOF
)
gh issue create --repo "$REPO" \
  --title "Add SSRF URL validation to scraper endpoints" \
  --label "type: tech-debt,area: backend,area: knowledge,priority: critical,size: M" \
  --milestone "Security Hardening" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
Plain SHA-256 is used for Fernet key derivation without salt. Should use PBKDF2 or Argon2.

## Acceptance Criteria
- [ ] Replace plain SHA-256 with PBKDF2 or Argon2 for Fernet key derivation
- [ ] Add salt to derivation
- [ ] Backward-compatible migration for existing encrypted data
- [ ] Update `core/encryption.py:22-26`

## Context
From Code Health scan Phase 1 — Security Hardening.
EOF
)
gh issue create --repo "$REPO" \
  --title "Strengthen key derivation — replace SHA-256 with PBKDF2/Argon2" \
  --label "type: tech-debt,area: backend,priority: high,size: M" \
  --milestone "Security Hardening" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
New endpoints default to open unless `require_scope` is manually added. No automated check catches a forgotten lock.

## Acceptance Criteria
- [ ] Test or pre-commit check that every route handler in `/api/` (except exempt paths) has a `require_scope` dependency
- [ ] List of exempt paths maintained in the test/check
- [ ] CI-friendly (exit non-zero on violation)

## Context
From Code Health scan Phase 1 — prevents "forgotten lock" regressions.
EOF
)
gh issue create --repo "$REPO" \
  --title "Add auth scope lint check for API endpoints" \
  --label "type: tech-debt,area: api,area: backend,priority: high,size: S" \
  --milestone "Security Hardening" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
Multiple security items from the optimization scan remain:
- Path traversal: validate file paths from `selected_files` JSON resolve within upload dir (`indexers/file.py:106`)
- File upload magic byte validation: verify content matches extension (`api/knowledge/sources.py:187-193`)
- GitHub token redaction: tokens in `KnowledgeSource.description` JSON returned unmasked (`indexers/github.py:489-506`)
- Request body size limits: no middleware cap on JSON body size (file uploads already capped)

## Acceptance Criteria
- [ ] Path traversal validation on file indexer
- [ ] Magic byte validation for uploads
- [ ] GitHub tokens redacted from API responses
- [ ] JSON body size limit middleware added

## Context
From Code Health scan Phase 1 — remaining security items that can be addressed together.
EOF
)
gh issue create --repo "$REPO" \
  --title "Address remaining security scan items (path traversal, magic bytes, token redaction, body limits)" \
  --label "type: tech-debt,area: backend,area: api,priority: high,size: M" \
  --milestone "Security Hardening" \
  --body "$body"

# --- Code Health ---

body=$(cat <<'EOF'
## Problem
9 extension models (`MigrationCampaign`, `MigrationProgram`, etc.) still live in core `models.py`. This violates the core isolation rule — core must never import from extensions.

## Acceptance Criteria
- [ ] Extension models extracted from core `models.py`
- [ ] Core `models.py` contains only core Agentbase models
- [ ] Extension strings removed from core utilities (`agent_service.py:77-78`, `core/utils.py:21-22`)
- [ ] `models.py` split if still >800 lines after extraction
- [ ] Alembic migration if needed

## Context
From Code Health scan Phase 2 — Core Isolation Cleanup. Critical for maintaining the separation between agentbase core and extensions.
EOF
)
gh issue create --repo "$REPO" \
  --title "Extract extension models from core models.py" \
  --label "type: tech-debt,area: backend,priority: high,size: M" \
  --milestone "Code Health" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
Several async functions use synchronous `open()`/`write()` which blocks the event loop.

## Locations
- `mcp/tools/knowledge.py:373`
- `mcp/tools/knowledge.py:515`
- `mcp/tools/knowledge.py:638`
- `indexers/file.py:106`

## Acceptance Criteria
- [ ] Replace blocking file I/O with `aiofiles` at all 4 locations
- [ ] Add `aiofiles` to `requirements.txt`
- [ ] No synchronous file operations remain in async code paths

## Context
From Code Health scan Phase 3 — Backend Code Quality.
EOF
)
gh issue create --repo "$REPO" \
  --title "Replace blocking file I/O with aiofiles in async functions" \
  --label "type: tech-debt,area: backend,area: mcp,priority: medium,size: S" \
  --milestone "Code Health" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
- `scrape_pages()` missing browser cleanup `try/finally` — `scan_url()` has it but `scrape_pages()` doesn't (`web_scraper/scraper.py:204-224`)
- `execute_indexing()` catches exceptions and updates status but doesn't rollback partial work (`ingestion/orchestrator.py:180-208`)
- `validate base64 size before decoding` — entire file decoded into memory before size check (`mcp/tools/knowledge.py:355-365`)
- `generate_api_key()` has minimal error handling for DB failures (`api/agents/api_keys.py:17-30`)

## Acceptance Criteria
- [ ] Browser cleanup in `scrape_pages()` via try/finally
- [ ] Transaction rollback on indexing error
- [ ] Base64 encoded string length checked before decoding
- [ ] API key generation error handling improved

## Context
From Code Health scan Phase 3 — Backend Code Quality.
EOF
)
gh issue create --repo "$REPO" \
  --title "Fix error handling gaps: browser cleanup, indexing rollback, base64 validation" \
  --label "type: tech-debt,area: backend,priority: medium,size: M" \
  --milestone "Code Health" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
- `KnowledgePage.tsx:114`: unstable useEffect dependency — `sources.filter().map().join()` creates new string every render, causing constant re-polling. Extract to `useMemo`.
- `ProvidersPage.tsx:93`: async fetches with no abort controller cleanup on unmount.
- `ProvidersPage.tsx`: 587/600 lines, approaching hard limit — consider splitting.
- `SettingsPage.tsx:77`: TODO referencing missing `GET /api/config` endpoint.

## Acceptance Criteria
- [ ] KnowledgePage useEffect dependency stabilized with useMemo
- [ ] AbortController added to ProvidersPage async effects
- [ ] ProvidersPage split if over 600 lines
- [ ] GET /api/config endpoint implemented or TODO removed

## Context
From Code Health scan Phase 4 — Frontend Code Quality.
EOF
)
gh issue create --repo "$REPO" \
  --title "Fix frontend code quality issues (useEffect, abort controllers, page splitting)" \
  --label "type: tech-debt,area: frontend,priority: medium,size: M" \
  --milestone "Code Health" \
  --body "$body"

# --- RAG Pipeline ---

body=$(cat <<'EOF'
## Problem
RAG pipeline has sequential Qdrant queries (N sources = Nx latency), standard search is default despite hybrid being implemented, no taxonomy metadata, and chunks only exist in Qdrant.

## Steps
1. **Parallelize Qdrant search** — `asyncio.gather()` + `asyncio.to_thread()` in `search_standard()` and `search_hybrid()` (`rag/search.py`)
2. **Default to hybrid search** — Change default from `search_standard` to `search_hybrid` (0.7 vector + 0.3 keyword) (`rag/context.py`)
3. **Add `search_mode` to Agent model** — New column: `standard`, `hybrid`, `multi_embedding`; pass through to RAG service
4. **Add source-level taxonomy tags** — `content_tags` JSON field on `KnowledgeSource`; inherited into chunk payloads; enables filtered search

## Key Files
- `backend/app/services/rag/search.py`
- `backend/app/services/rag/context.py`
- `backend/app/models/models.py`
- `backend/app/services/ingestion/indexers/base.py`

## Context
See BACKLOG.md "RAG Optimization: Multi-Source Search" for full design.
EOF
)
gh issue create --repo "$REPO" \
  --title "RAG optimization: parallel search, hybrid default, taxonomy tags" \
  --label "type: feature,area: rag,area: backend,priority: high,size: L" \
  --milestone "RAG Pipeline" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
Chunks only exist in Qdrant. No SQL-level access for comparison, auditing, export, or debugging retrieval context.

## Acceptance Criteria
- [ ] New `chunks` table: `id`, `source_id`, `collection_name`, `chunk_index`, `content`, `content_hash`, `metadata` (JSON), `created_at`
- [ ] Dual-write in `_process_embedding_batch()` — write to both Qdrant and Postgres
- [ ] Alembic migration for new table
- [ ] Index on `source_id` and `content_hash`

## Context
See BACKLOG.md "Chunk Storage in PostgreSQL". Build when real technical content is being ingested and there's a need to query/audit chunks.
EOF
)
gh issue create --repo "$REPO" \
  --title "Store indexed chunks in PostgreSQL for auditing and comparison" \
  --label "type: feature,area: rag,area: backend,priority: high,size: M" \
  --milestone "RAG Pipeline" \
  --body "$body"

# --- Knowledge Lifecycle ---

body=$(cat <<'EOF'
## Problem
No way to know whether indexed content still reflects source material. URLs indexed months ago may have changed, GitHub repos may have new commits, and uploaded files may have been superseded. No visibility or mechanism to act on this.

## Features
1. **Freshness tracking** — `last_indexed_at`, `freshness_policy`, `stale_after_days` fields; badges in UI
2. **Scheduled re-indexing** — Cron-style refresh per source via job queue
3. **Change detection** — Content hash comparison for URLs, commit SHA for GitHub
4. **Staleness alerts** — Dashboard summary, SSE notifications
5. **Lifecycle actions** — Archive (frozen), Retire (soft-delete), Bulk refresh

## Data Model Changes
```python
freshness_policy: Optional[str]     # "scheduled", "manual", "frozen"
stale_after_days: Optional[int]      # Threshold (default: 90)
refresh_interval_days: Optional[int] # For scheduled policy
last_indexed_at: Optional[datetime]
content_hash: Optional[str]
retired_at: Optional[datetime]
```

## Context
See BACKLOG.md "Knowledge Freshness & Lifecycle" for full design, key files, and implementation sequence.
EOF
)
gh issue create --repo "$REPO" \
  --title "Knowledge freshness tracking, scheduled re-indexing, and lifecycle management" \
  --label "type: feature,area: knowledge,area: backend,area: frontend,priority: high,size: XL" \
  --milestone "Knowledge Lifecycle" \
  --body "$body"

# --- Platform Features ---

body=$(cat <<'EOF'
## Problem
RAG pipeline only supports PDF and web content. DOCX, PPTX, XLSX, CSV, TXT, and MD files cannot be ingested.

## Formats to Add
| Format | Library | Notes |
|--------|---------|-------|
| DOCX | `python-docx` | Word documents, preserve headings |
| PPTX | `python-pptx` | PowerPoint slides, extract text + notes |
| XLSX | `openpyxl` | Spreadsheets, sheet-by-sheet extraction |
| CSV | Built-in `csv` | Row-based chunking |
| TXT/MD | Built-in | Standard recursive text chunking |

## Files to Create
- `backend/app/loaders/docx_loader.py`
- `backend/app/loaders/pptx_loader.py`
- `backend/app/loaders/spreadsheet_loader.py`

## Context
See BACKLOG.md "Expanded File Format Support (Phase 5.7)".
EOF
)
gh issue create --repo "$REPO" \
  --title "Add expanded file format support (DOCX, PPTX, XLSX, CSV, TXT, MD)" \
  --label "type: feature,area: knowledge,area: backend,priority: medium,size: M" \
  --milestone "Platform Features" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
API documentation lives in `API.md` — only accessible by reading the file. Developers and agents should be able to browse API reference within the UI.

## Acceptance Criteria
- [ ] `/api-reference` page rendering API.md with markdown formatting
- [ ] Syntax highlighting for code blocks
- [ ] Table of contents sidebar navigation
- [ ] Search/filter endpoints
- [ ] Copy-to-clipboard for curl examples

## Context
See BACKLOG.md "API Reference Page (UI)" for full design and UI layout mockup.
EOF
)
gh issue create --repo "$REPO" \
  --title "Add in-app API Reference page" \
  --label "type: feature,area: frontend,priority: medium,size: M" \
  --milestone "Platform Features" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
No strategy for managing development vs production instances of Agentbase.

## Design Considerations
- Database isolation (separate instances or schemas?)
- Qdrant isolation (prefixed collections or separate instances?)
- Environment configuration switching
- Extension versioning across environments
- Data migration/promotion process

## Acceptance Criteria
- [ ] Environment configuration architecture designed
- [ ] Environment-specific Docker Compose files
- [ ] Environment switching procedure documented
- [ ] Deployment checklist for production
- [ ] CI/CD pipeline considerations defined

## Context
See BACKLOG.md "Dev/Prod Instance Management Plan".
EOF
)
gh issue create --repo "$REPO" \
  --title "Design dev/prod instance management strategy" \
  --label "type: infra,area: infra,status: needs-design,priority: medium,size: L" \
  --milestone "Platform Features" \
  --body "$body"

# --- Active Sprint ---

body=$(cat <<'EOF'
## Items
- [ ] Providers page model toggle — verify working in Docker build (tested via Playwright)
- [ ] Google provider card — needs API key testing
- [ ] Increase URL source selectable pages cap from 1000 to 25000 (sitemap discovery)
- [ ] Project-level default model assignment via ModelAssignment table

## Context
See BACKLOG.md "Quick Fixes & Polish".
EOF
)
gh issue create --repo "$REPO" \
  --title "Quick fixes: provider toggle, Google testing, URL cap, project default model" \
  --label "type: enhancement,area: frontend,area: providers,priority: high,size: M" \
  --milestone "Active Sprint" \
  --body "$body"

body=$(cat <<'EOF'
## Problem
MCP server needs review for completeness, error handling, and documentation of available tools.

## Tasks
- [ ] Audit current MCP tool implementations for completeness
- [ ] Test MCP server with Claude Code integration
- [ ] Document available MCP tools and their parameters
- [ ] Identify missing tools for common workflows
- [ ] Review error handling and response formats
- [ ] Consider adding tools for RAG search with filters and prompt management

## Key Files
- `backend/app/mcp/server.py`
- `backend/app/mcp/tools/*.py`
- `.mcp.json`

## Context
See BACKLOG.md "MCP Server Review".
EOF
)
gh issue create --repo "$REPO" \
  --title "MCP server review: completeness audit and tool documentation" \
  --label "type: enhancement,area: mcp,priority: medium,size: M" \
  --milestone "Active Sprint" \
  --body "$body"

# --- Distribution & Scale ---

body=$(cat <<'EOF'
## Description
Package Agentbase for easy deployment and consumption:
- Helm chart for Kubernetes
- Python SDK for programmatic access
- Documentation site (standalone)
- CLI tool for admin operations

## Context
See BACKLOG.md Phase 9. Long-term goal.
EOF
)
gh issue create --repo "$REPO" \
  --title "Distribution: Helm chart, SDKs, documentation site" \
  --label "type: feature,area: infra,priority: low,size: XL" \
  --milestone "Distribution & Scale" \
  --body "$body"

body=$(cat <<'EOF'
## Description
Scale Agentbase for multi-tenant deployment:
- Multi-tenancy with tenant isolation
- OAuth2/OIDC integration (Google, GitHub, enterprise SSO)
- Per-user API keys and project scoping
- Resource quotas and usage tracking

## Context
See BACKLOG.md Phase 10. Long-term goal.
EOF
)
gh issue create --repo "$REPO" \
  --title "Scale: multi-tenancy, OAuth2/OIDC, resource quotas" \
  --label "type: feature,area: backend,area: api,priority: low,size: XL" \
  --milestone "Distribution & Scale" \
  --body "$body"

echo ""
echo "Seed issues created"
echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Create the project board:  gh project create --owner skiboy10 --title 'Agentbase'"
echo "  2. Link the project to the repo in GitHub settings"
echo "  3. Add existing issues to the project board"
echo "  4. Share the AGENT_GUIDE.md with your team so their Claude agents know how to interact with the backlog"
