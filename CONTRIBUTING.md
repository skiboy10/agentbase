# Contributing to Agentbase

Thank you for your interest in contributing to Agentbase, an open-source knowledge curation engine. This guide covers everything you need to get a development environment running and land a pull request.

## Development Setup

Agentbase is developed entirely inside Docker Compose. You need Docker (with Compose v2) installed; no local Python or Node toolchain is required for day-to-day work.

```bash
git clone https://github.com/skiboy10/agentbase.git
cd agentbase
docker compose up -d
```

Services and ports:

| Service | Port | Notes |
|---------|------|-------|
| Frontend (React/Vite) | 3002 | Production build served from the container |
| Backend (FastAPI) | 8002 | Health check: `curl http://localhost:8002/health` |
| PostgreSQL | 5434 | Application database |
| Qdrant | 6335 (optional) | Vector store. Points at an external instance by default (`QDRANT_URL`); start the bundled one with `docker compose --profile with-qdrant up -d` |

### Making changes

- **Backend** (`backend/app/`): hot-reloads automatically via a volume mount. Edit files and the server restarts itself — no rebuild needed.
  - Exception: `backend/scripts/` is baked into the image, not mounted. Changes there require `docker compose build backend && docker compose up -d backend`.
- **Frontend** (`frontend/src/`): the container serves a production build, so changes require a rebuild:
  ```bash
  docker compose build frontend && docker compose up -d frontend
  ```
- **New backend dependencies**: add them to `backend/requirements.txt`, then rebuild the backend container.

### Machine-specific configuration stays local

Never commit instance configuration. The following are machine-specific and must remain local (they are gitignored — keep them that way):

- `docker-compose.override.yml` — local volume paths, data directory redirects, port tweaks
- `.env` files — secrets, API keys, hostnames
- Data directories — Postgres data, Qdrant storage, uploads

If you find yourself needing to commit a change to make your local setup work, put it in `docker-compose.override.yml` instead.

### Pre-commit hooks and the private-terms scan

Enable the repo's commit guards once per clone:

```bash
./scripts/setup-git-hooks.sh
```

The pre-commit hook blocks data files, `.env` files, and oversized binaries. It also supports an **optional local denylist** for your own sensitive vocabulary — client names, internal hostnames, usernames — so they can never ride along in a commit:

```bash
# One term per line, matched case-insensitively; '#' comments allowed
cat > .git/private-terms.txt <<'EOF'
# my sensitive terms
internal-project-codename
bigclient
EOF
```

The file lives inside `.git/`, so it is never committed and is shared automatically by all your worktrees. If the hook blocks a term you intended (e.g. in a test fixture), fix the wording — or bypass consciously with `git commit --no-verify`.

## Running Tests

Backend tests run inside the container against SQLite (no Postgres or Qdrant required):

```bash
docker compose exec backend pytest tests/ -x
```

Run these after any change under `backend/app/`. For the frontend, verify the production build compiles (this also runs the TypeScript compiler):

```bash
docker compose build frontend
```

CI runs the same checks on every pull request: backend pytest, frontend `npm run build` (which includes `tsc`), and a secret scan.

## Pull Request Conventions

### Branch naming

Create a branch named for the type of change:

- `feat/<short-description>` — new features
- `fix/<short-description>` — bug fixes
- `chore/<short-description>` — tooling, docs, dependencies, refactors

### Commit messages

We use Conventional Commits style, matching the existing history:

```
feat(evaluation): add scorecard comparison view
fix(ingestion): route library-bound source chunks to the source collection
chore(deps): upgrade sqlalchemy to 2.0.50
```

Format: `type(scope): imperative summary`. Common types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`.

### Merging

Pull requests are **squash-merged** to `main` once CI is green. Your PR title becomes the commit message, so give it the same `type(scope): summary` format. Releases are tagged from `main`.

## Code Style

### Backend (Python 3.11 / FastAPI)

- Type hints on all function signatures
- `async`/`await` throughout — no blocking calls in request handlers
- Pydantic models for request/response schemas and configuration

### Frontend (React 18 / TypeScript)

- TypeScript strict mode — no `any` escapes
- Functional components with hooks (no class components)
- shadcn/ui + Radix UI primitives for components
- **Design tokens only, no raw palette colors**: colors resolve through CSS variables (`index.css` → `tailwind.config.js`). Never use raw Tailwind palette classes like `bg-blue-900` or `text-green-600`.

### File size guidelines

Keep files small enough for both humans and AI agents to understand and modify safely:

| Type | Target (lines) | Hard Limit |
|------|----------------|------------|
| Backend Service | 300-500 | 800 |
| Backend Router | 200-400 | 600 |
| Frontend Page | 200-400 | 600 |
| Frontend Component | 100-200 | 400 |

When a file outgrows its limit, split it: create a same-name directory, add a barrel export (`__init__.py` / `index.ts`), and break the logic into focused modules.

### General

- No emojis in code, comments, or documentation.

## Examples and Placeholder Hygiene

Agentbase source code and documentation are read by external users and agents. Helper text, placeholders, example payloads, code comments, docstrings, test fixtures, and docs **must not reference real companies, clients, vendors, or individuals**.

- Use `ACME` (e.g., `ACME Corp`, `ACME Q4 Plan`) as the generic organization name
- Use `Jane Doe` / `John Doe` for example individuals
- Use generic product names (`Product Documentation`, `Sales Playbook`) where possible
- Use `example.com` for example URLs

This applies to `placeholder=` attributes, `e.g., ...` strings, JSON examples, docstring examples, and test fixture paths. If you are unsure whether a name is real, treat it as real and replace it.

## Reporting Issues

- **Bugs and feature requests**: open a GitHub issue using the provided templates.
- **Security vulnerabilities**: do not open a public issue — see [SECURITY.md](SECURITY.md).

## License

By contributing to Agentbase, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
