# Upgrading a Live Agentbase Instance

Run production (or personal live) instances from **release tags**, never from
`main`. `main` moves with every merged PR; tags are the tested checkpoints.
This keeps day-to-day development — including branch switches and in-progress
migrations — from ever touching a running instance.

## Standard upgrade

```bash
cd <your-agentbase-checkout>
git fetch --tags
git checkout vX.Y.Z          # the release you are upgrading to

docker compose build          # backend scripts and frontend are baked into images
docker compose up -d          # recreates containers; use up -d, NOT restart
```

Notes:

- **Database migrations run automatically** on backend startup
  (`alembic upgrade head`). No manual migration step.
- **Use `up -d`, not `restart`** — `restart` reuses the old container and does
  not pick up new images or changed environment values.
- **A rebuild is required, not optional.** Only `backend/app`, `backend/tests`,
  and `backend/alembic` are volume-mounted for development; `backend/scripts`,
  dependencies, and the frontend bundle ship inside the images.

## Your local configuration is never touched

Instance-specific files stay out of git and survive every upgrade:

- `.env` — secrets and provider keys
- `docker-compose.override.yml` — data paths, extra mounts, port overrides
- your data directories (Postgres, Qdrant, uploads)

If an upgrade adds new settings, `.env.example` shows them — compare and copy
what you need:

```bash
git diff vOLD..vNEW -- .env.example
```

## Verifying an upgrade

```bash
curl http://localhost:8002/health     # backend + provider status
docker compose logs backend | tail    # watch for migration/startup errors
```

## Rolling back

```bash
git checkout vPREVIOUS
docker compose build
docker compose up -d
```

Database migrations are forward-only. The backend tolerates a database that is
*ahead* of the checked-out code (extra tables and columns are ignored), so
rolling back the code without rolling back the schema is safe. If a release
notes a breaking migration, restore the database from a backup taken before
upgrading instead.

## Qdrant image upgrades

The optional Compose Qdrant service is pinned (e.g. `qdrant/qdrant:v1.19.2`),
not `:latest`. When bumping the pin, upgrade **one minor at a time** (for
example 1.17 → 1.18 → 1.19) — Qdrant storage format changes
(RocksDB → Gridstore) and gRPC field removals can break direct jumps.

If you set `QDRANT_API_KEY` in `.env`, the included Qdrant container and the
backend (`qdrant_api_key` / `QDRANT_API_KEY`) must share the same value.

### Hybrid search / sparse BM25 (#33)

New collections are created with a named sparse vector `bm25` (IDF) alongside
the dense embedding, and the `content` text index uses English stopwords +
Snowball stemming. Hybrid search prefers server-side RRF of dense + BM25
Prefetch when that sparse schema is present.

**Existing collections** keep working: search falls back to dense + `MatchText`
Prefetch (or Python RRF) until you re-index. To pick up sparse BM25:

1. Confirm Qdrant is on **v1.15.3+** (Compose pin is `v1.19.2`).
2. Re-index each source (`POST /api/sources/{id}/index` or MCP
   `agentbase_index_source`). The indexer adds the `bm25` schema via
   `update_collection` if missing, then upserts points with both dense and
   BM25 vectors.
3. Optional: recreate the collection (full re-index with delete) if you also
   want the upgraded text-index stemming/stopwords on `content` — payload
   index options are not rewritten in place for older collections.

No Alembic migration is involved; this is Qdrant-only schema + payload data.

## For contributors

Development never happens in a live checkout. See
[CONTRIBUTING.md](CONTRIBUTING.md): work in a git worktree on a branch, open a
PR, let CI pass, merge — and live instances pick the change up at the next
tagged release.
