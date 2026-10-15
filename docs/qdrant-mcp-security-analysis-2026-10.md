# Agentbase Analysis — Qdrant · MCP · Security (2026-10)

Snapshot of the live product against current Qdrant capabilities, MCP readiness,
and security posture. Backlog actions taken from this review are tracked as
GitHub Issues (see [BACKLOG.md](../BACKLOG.md)).

Sources: codebase on `main`, GitHub Issues, Qdrant release notes/blogs for
v1.13–v1.19 (2025-01 through 2026-10).

---

## 1. Qdrant usage vs current feature state

### What Agentbase uses today

| Capability | Status |
|------------|--------|
| Dense cosine collections (`VectorParams`) | Used — one collection per source |
| Full-text payload index on `content` (WORD tokenizer) | Used at collection create |
| Keyword / integer payload indexes for metadata filters | Used (`KEYWORD_INDEX_FIELDS`) |
| `query_points` dense search | Used (standard / multi-embedding) |
| Hybrid = dense + `MatchText` + Python weighted RRF | Used — **native Prefetch/FusionQuery disabled** |
| `query_groups` (diversity by `metadata.file_id`) | Detected + used with fallback |
| App-side cross-encoder rerank (FlashRank / Ollama) | Used |
| Sparse / BM25 named vectors | **Not used** |
| Quantization (scalar / binary / TurboQuant) | **Not used** |
| Formula / score-boost / relevance-feedback queries | **Not used** |
| MMR diversity at Qdrant layer | **Not used** (app grouped search only) |
| Memory tiers / inline HNSW / ACORN | **Not configured** |
| Pinned Qdrant server version | **`qdrant/qdrant:latest`** (unpinned) |
| Client pin | `qdrant-client>=1.18.0` |

Client singletons are duplicated in three modules (`rag/client.py`,
`ingestion/qdrant_client.py`, `embedding_processor.py`).

### Hybrid search gap (highest impact)

`search_hybrid` documents native server-side RRF via `Prefetch` + `FusionQuery`,
but `_SUPPORTS_NATIVE_FUSION` is hard-disabled (`pass` after a commented check)
in `backend/app/services/rag/search.py`. The live path:

1. Dense `query_points`
2. Unranked `scroll` + `MatchText` (placeholder score `1.0`)
3. Python `weighted_rrf`

That is weaker than Qdrant’s current hybrid model (dense + sparse BM25, prefetch
fusion, weighted RRF, optional IDF corpus scoping in 1.19). Text “ranking” via
scroll order is not BM25.

### Qdrant releases since early 2025 (relevant to Agentbase)

| Version | When | Features Agentbase should care about |
|---------|------|--------------------------------------|
| **1.13** | 2025-01 | GPU HNSW, strict mode, mmap defaults |
| **1.14** | 2025-04 | Score-boosting reranker, incremental HNSW, faster batch search |
| **1.15** | 2025-07 | Better text index (stemming, stopwords, phrase, multilingual), MMR, smarter quantization |
| **1.16** | 2025-11 | ACORN filtered search, tiered multitenancy, `text_any`, conditional updates |
| **1.17** | 2026-02 | Relevance feedback, weighted RRF, audit logging, formula-adjacent scoring path |
| **1.18** | 2026-05 | TurboQuant, add/remove named vectors without recreate, memory monitoring |
| **1.19** | 2026-≈09/10 | TurboQuant-as-datatype, memory tiers, prefix keyword match, per-query IDF corpus, slice filter |

### Recommendations (priority order)

1. **Re-enable native Prefetch + FusionQuery** against the pinned server; verify
   `query_filter` on Prefetch with the deployed version.
2. **Add named sparse BM25 vectors at index time** and fuse dense+sparse (true
   hybrid). Use IDF modifier; consider per-library/tenant IDF corpus when filters
   scope a subset.
3. **Upgrade text payload index** to stemming + stopwords (+ phrase where useful).
4. **Pin `qdrant/qdrant` image** to a minor (e.g. `v1.19.x`), not `latest` — RocksDB→Gridstore
   and gRPC vector-field changes make unpinned upgrades risky.
5. **Optional quantization** (scalar first, TurboQuant for large corpora) once
   recall is measured via evaluation scorecards.
6. **Consolidate `get_qdrant_client`** to one module.
7. Defer: relevance feedback / formula boosts (needs product UX), tiered
   multitenancy (single-tenant self-host is fine with per-source collections),
   ACORN (only if filtered-search quality regressions appear).

Related latent bug: `search_grouped` logs `_qdrant_version` on the fallback path
but that name is never defined → `NameError` if `query_groups` is unsupported.

---

## 2. MCP capabilities — health & readiness

### Inventory

- **84** `agentbase_*` tools across auth, projects, agents, libraries, sources,
  source_ops, sources_docs, sources_upload, taxonomy, evaluation, guide, discovery.
- FastMCP `stateless_http=True`, DNS-rebinding protection via
  `TransportSecuritySettings`, mounted at `/mcp` behind `_MCPAuthWrapper`.
- Write tools call `check_mcp_scope(Scope.WRITE)` (fail-closed when contextvar
  missing — closed in #11). Bootstrap key tool intentionally unscoped until
  first key exists.
- Knowledge Librarian skill (`.claude/skills/knowledge-librarian/`) drives the
  full curation lifecycle through MCP — partially delivers the “agentic curation”
  vision in #4 as an external agent pattern rather than in-product automation.

### Readiness verdict: **production-capable for operator/agent workflows; not yet a polished public MCP product**

| Strength | Gap |
|----------|-----|
| Broad CRUD + RAG + eval/experiment surface | No MCP progress streaming for long jobs (poll-only; documented) |
| Scope hierarchy + connection-level external gate | Per-key `rate_limit_rpm` stored but not enforced (#10) |
| Guide + discovery tools for agent onboarding | `docs/mcp-remediation-plan.md` stale (issues #11/#9/#5 closed) |
| Annotations (`readOnlyHint`, etc.) present | Some list tools historically had pagination clamps; verify remaining |
| Evaluation + promote experiment via MCP | No dedicated MCP smoke suite in CI called out as a gate |

### Recommendations

1. Keep MCP auth/scope lint tests green as a merge gate.
2. Enforce #10 rate limits on both REST middleware and `_MCPAuthWrapper`.
3. Treat Knowledge Librarian + MCP as the supported “agentic curation” path;
   re-scope #4 to in-product automation only where the skill cannot reach.
4. Archive completed remediation plan; add a short MCP readiness checklist to
   Quickstart / skills page.

---

## 3. Security review

### Strengths (already shipped)

- Bearer + Argon2id platform API keys with `read`/`write`/`admin` scopes
- MCP fail-closed scope checks + WebSocket gating (#11 / prior tunnel work)
- Secret-gated `X-Forwarded-For` rewriting (`internal_forward_secret`)
- Docker bridge removed from default `trusted_networks`
- SSRF protection (`url_validator` + Playwright route guard + httpx fallback)
- Fernet encryption for provider credentials; ephemeral SECRET_KEY warning
- Swagger/OpenAPI hidden unless `debug_mode`
- Path containment for uploads / skills zip
- CORS rejects `*` + credentials combination

### Findings

| Sev | Finding | Notes |
|-----|---------|-------|
| **M** | `APIKey.rate_limit_rpm` not enforced | Already #10 |
| **M** | Qdrant Compose service unpinned (`:latest`) and typically no Qdrant API key | Footgun for upgrades + open vector DB if port exposed |
| **M** | Empty/default `SECRET_KEY` only **logs** critically when combined with known defaults + `EXTERNAL_HOSTNAME`; empty key still boots with ephemeral key even if externally exposed | Prefer refuse-to-start when `external_hostname` set and SECRET_KEY missing/insecure |
| **L** | LAN/`trusted_networks` open access by design | Correct for self-host; document threat model for tunnel misconfig |
| **L** | Directory sources can index any path visible inside the container | Expected; keep volume mounts intentional |
| **L** | `/health` returns `providers_configured` | Low info disclosure |
| **I** | Duplicate Qdrant clients / disabled native fusion | Reliability & quality, not authz |

No critical unauthenticated RCE/SSRF path found in this pass; prior hardening
(#49-era proxy secret, SSRF, MCP auth) looks effective. Residual risk is mostly
**operational misconfiguration** and **unenforced documented controls** (#10).

---

## 4. Backlog hygiene (actions from this review)

### Created (agent token can create issues; cannot edit labels/milestones/comments)

| Issue | Title | Intended labels | Intended milestone |
|-------|-------|-----------------|--------------------|
| [#33](https://github.com/skiboy10/agentbase/issues/33) | Enable native Qdrant hybrid fusion + sparse BM25 vectors | `type: enhancement`, `area: rag`, `priority: high`, `size: L` | RAG Pipeline |
| [#34](https://github.com/skiboy10/agentbase/issues/34) | Pin Qdrant image, consolidate client, fix `_qdrant_version` | `type: infra`, `area: infra`, `area: rag`, `priority: high`, `size: M` | Security Hardening |
| [#35](https://github.com/skiboy10/agentbase/issues/35) | Refuse startup with insecure SECRET_KEY when exposed | `type: enhancement`, `area: api`, `area: infra`, `priority: high`, `size: S` | Security Hardening |
| [#36](https://github.com/skiboy10/agentbase/issues/36) | Re-scope agentic curation (#4) vs Knowledge Librarian skill | `type: docs`, `area: knowledge`, `area: mcp`, `priority: medium`, `size: S`, `status: needs-design` | Platform Features |

Also close stray [#32](https://github.com/skiboy10/agentbase/issues/32) (accidental empty test create).

### Maintainer follow-ups (token lacked `addLabels` / `updateIssue` / `addComment`)

1. Apply labels + milestones in the table above to #33–#36.
2. Fix #26 malformed labels (`type:bug` → `type: bug`, `area:backend` → `area: backend`, `priority:medium` → `priority: medium`); add `area: knowledge`; milestone **Active Sprint**.
3. Assign milestones to existing opens: #20/#21/#26 → Active Sprint; #10/#34/#35 → Security Hardening; #6/#7 → Knowledge Lifecycle; #3/#4/#36 → Platform Features; #8 → Code Health; #1/#33 → RAG Pipeline; #2 → Distribution & Scale.
4. Optional triage comments on #3 (still single-shot UI), #4 (skill partial), #20/#21/#26 (confirm still valid).
5. `docs/mcp-remediation-plan.md` stubbed as COMPLETED (#11/#9/#5 closed).
