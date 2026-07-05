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

## For contributors

Development never happens in a live checkout. See
[CONTRIBUTING.md](CONTRIBUTING.md): work in a git worktree on a branch, open a
PR, let CI pass, merge — and live instances pick the change up at the next
tagged release.
