## Summary

<!-- What does this PR do, and why? A few sentences is enough. -->

## Linked Issue

<!-- Link the issue this PR addresses, e.g. "Closes #123". If there is no issue, briefly explain why. -->

Closes #

## Changes

<!-- Bullet list of the notable changes. -->

-

## Test Evidence

<!-- Check what applies and paste relevant output. -->

- [ ] Backend tests pass: `docker compose exec backend pytest tests/ -x`
- [ ] Frontend production build compiles: `docker compose build frontend`
- [ ] Manually verified the change in the running app (describe below)
- [ ] No backend/frontend code changed (docs, CI, or tooling only)

<!-- Paste test output or describe manual verification steps here. -->

## Checklist

- [ ] Branch is named `feat/*`, `fix/*`, or `chore/*`
- [ ] PR title follows Conventional Commits (`type(scope): summary`) — it becomes the squash-merge commit message
- [ ] No machine-specific config committed (`.env`, `docker-compose.override.yml`, data directories)
- [ ] Examples and placeholders use generic names (ACME, Jane Doe), not real organizations or people
- [ ] Documentation updated if behavior or APIs changed (API.md, ARCHITECTURE.md)
