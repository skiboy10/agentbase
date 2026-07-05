# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities **privately** through GitHub Security Advisories:

1. Go to the [Security tab](https://github.com/skiboy10/agentbase/security) of this repository
2. Click **"Report a vulnerability"**
3. Fill in the details: affected component, reproduction steps, and impact

Do **not** open a public issue or pull request for security problems — that discloses the vulnerability before a fix is available.

You can expect an initial response within approximately 7 days. We will keep you informed as we triage, develop a fix, and coordinate disclosure.

## Supported Versions

Only the **latest minor release** receives security fixes. If you are running an older version, upgrade to the latest release before reporting — the issue may already be resolved.

| Version | Supported |
|---------|-----------|
| Latest minor release | Yes |
| Older releases | No |

## Scope

Agentbase is designed to run as a self-hosted service. Reports are most valuable when they concern:

- Authentication or authorization bypass (API keys, MCP scopes, trusted-network handling)
- Injection vulnerabilities (SQL, command, prompt injection affecting system integrity)
- Server-side request forgery (SSRF) in the ingestion or scraping pipeline
- Secrets exposure (credentials at rest or in transit)
- Container escape or privilege escalation within the Docker Compose stack

Deployment misconfigurations on a user's own infrastructure (for example, exposing the backend port directly to the internet without a reverse proxy) are documented hardening concerns rather than vulnerabilities, but reports that reveal unsafe defaults are welcome.

## Disclosure

We ask that you give us a reasonable window to release a fix before public disclosure. We will credit reporters in the release notes if desired, but we do not operate a bug bounty or hall-of-fame program.
