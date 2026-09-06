# MCP remediation plan — issues #11, #9, #5

Branch: `fix/mcp-hardening` (worktree `../agentbase-mcp-hardening`, based on `origin/main` including #22).
Closed out of scope: [#27](https://github.com/skiboy10/agentbase/issues/27) (Hermes read-only API key — ops, not product).

## Team

| Role | Owns | Never touches |
|------|------|----------------|
| Backend-Security | #11 — `backend/app/core/auth.py`, `backend/app/middleware/auth.py`, `backend/tests/test_mcp_auth_gate.py`, `backend/tests/test_auth_scope_lint.py` | `frontend/` |
| Backend-Tools | #9 — `backend/app/mcp/tools/*.py` and MCP-layer tests only | `frontend/`, auth middleware |
| Frontend | #5 Stage 2 UI — library source-add flow, API client 409 parsing | `backend/` except reading API error shape |
| QA | Docker pytest + frontend build after the three land | Source files (report only; orchestrator applies test-driven fixes) |
| Orchestrator | Integrate, AGY review, issue comments, docs | — |

Claude CLI is not spawnable in this session. Teammates are Grok agents filling the Agentbase Full-Stack Builder roles. Orchestrator runs Antigravity (`agy`) after integration — subagents must not invoke `agy`.

## #11 Harden MCP auth

Follow-ups from the pre-launch security review. #22 (tunnel-proxied requests require a key; WebSocket MCP gate) is already on this branch. Do not regress it.

1. **`check_mcp_scope()` fail-closed.** Today the unset-contextvar branch `return`s (fail-open). After #22 every admitted `/mcp` request has context set, and stateless HTTP inherits contextvars. Raise `ValueError` instead. Log a warning. Sweep/add tests that call tools with no auth context.
2. **Per-route AST lint.** `test_auth_scope_lint.py` is file-granular (`"require_scope" in source`). Upgrade so each `@router.<method>` handler has a `require_scope` dependency (or a documented exemption). A file with one protected route must not hide an unprotected sibling.
3. **`BearerTokenMiddleware` reset.** `_MCPAuthWrapper` already `set`/`reset`s the contextvar. Middleware currently `set_current_auth` without `reset_current_auth` in `finally` — leak into reused tasks. Apply the same token pattern.
4. Non-HTTP ASGI scopes stay ungated (fine). WebSocket is already gated by #22.

## #9 MCP tool edge cases

Verified still present on this branch:

- `agentbase_bind_knowledge_base`: service returns `None` for agent-missing, library-missing, *and* already-bound. Tool only special-cases missing agent, then reports `already_bound`. Distinguish all three.
- Pagination unclamped: `list_watcher_events`, `list_stale_sources`, `list_sources`, `list_libraries`, `list_agent_knowledge_bases` (and any sibling list tools with raw `limit`/`offset`). Clamp `offset >= 0`, `limit >= 1` via `Field` (match high-traffic tools).
- `agentbase_start_watcher`: proceeds when `get_source()` is `None`. Return source-not-found.
- `_library_to_dict` walks `kb.sources` — keep `selectinload` on every caller; do not lazy-load.
- `datetime.utcnow()` in `re_enrich_source` (~source_ops.py:501) — switch to timezone-aware UTC.

## #5 Stage 2 — UI + embedding-lock enforcement

Stage 1 is shipped (junction table, first-source lock, API/MCP `EMBEDDING_MISMATCH`). Remaining is UI:

- Library Settings already shows the locked embedding badge. Empty libraries (null embedding) should say the first bound source will lock the model.
- `SourcePicker` should disable (or warn on) sources whose `embedding_provider/model` do not match a locked library. Unlocked libraries accept any source.
- `POST /api/libraries/{id}/sources` returns 409 with `detail` as the structured dict (`error_code`, `detail`, `library`, `source`, `suggested_action`). `apiFetch` currently does `throw new Error(error.detail)`, which becomes `[object Object]` when `detail` is a dict. Parse that body and show the human `detail` + suggested action in the toast.
- Do not use raw Tailwind palette colors (`text-emerald-400` already exists in SettingsTab — do not add more). Status/tokens via CSS variables.
- Transient add failure → toast (`useToast`). No new ErrorBanner for this path.

## Verification

```bash
# After this branch is merged into the checkout that Docker volume-mounts:
docker compose exec backend pytest tests/test_mcp_auth_gate.py tests/test_auth_scope_lint.py tests/test_mcp_tools.py tests/test_agent_service.py -x --tb=short
```

Frontend: `docker compose build frontend` after UI changes. Exercise Library → Sources → add a mismatched source and a matching source.

## Out of scope

- Hermes key rotation (#27 closed)
- Unrelated dirty files on the main checkout (agent query, grok provider, docker-compose)
- Stage 2 re-embed-as-copy workflow (explicitly future in #5)
