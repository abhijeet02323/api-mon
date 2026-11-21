# SentinelAPI implementation report

## Delivered

- FastAPI REST service with OpenAPI, health/readiness endpoints, and a minimal browser dashboard.
- Account registration/login with salted PBKDF2 password hashes and opaque bearer sessions.
- Owner-scoped monitor create/list/detail/update/delete, manual check, history, incidents, acknowledgement, and resolution endpoints.
- SQLite persistence, a one-process periodic scheduler, per-monitor overlap prevention, bounded request timeout, disabled redirects, and no response-body persistence.
- DNS/IP checks block non-global destinations before monitor creation and before each request. Incidents open after two consecutive availability failures and resolve after a successful check.
- Docker app/Grafana setup, an example Grafana dashboard and datasource provisioning, environment template, backlog, and this report.

## Architecture and run instructions

FastAPI + httpx + SQLite in one container, with an in-process asyncio scheduler. Grafana runs as a separate Compose service. Start with `cp .env.example .env && docker compose up --build`. See the root README for account setup and usage.

## Verification

- `python -m py_compile app.py`: passed after fixing a syntax error found during initial validation.
- Grafana dashboard JSON parsing with Python's `json` module: passed.
- FastAPI/httpx runtime and endpoint tests: not run. The base environment has neither dependency installed and `python -m pip` is unavailable; dependency installation could not begin.
- UI → API → DB → result path, scheduler behavior, and incident transitions: not runtime verified.
- Docker Compose, Grafana datasource, PostgreSQL, AWS deployment, and CloudWatch: not verified. There are no application/database services or AWS credentials in this checkout.
- Git history/status/commit: not available. `.git` exists as an empty, read-only directory; `git status` reports “not a git repository.” No commit was created.

## Security review

Positive controls: password hashing, bearer auth, parameterized SQLite queries, ownership-scoped reads/updates/deletes, URL scheme and credential validation, public-IP-only DNS validation, redirect disabling, bounded request timeout, bounded input fields, and response-body omission.

Known gaps: no login or manual-check rate limiting, session expiry/revocation, TLS termination, database migrations, DNS pinning/egress proxy, global scheduler concurrency/rate limiting, or production CORS/security-header configuration. `is_global` checks reduce SSRF exposure but cannot stop DNS rebinding between resolution and connection. Do not expose this MVP to the public internet without network egress controls and a hardened deployment.

## Deployment and product gaps

AWS deployment was not attempted. The brief's P0 PostgreSQL requirement is not met: SQLite was selected to make the otherwise empty checkout runnable without provisioned infrastructure. Grafana files are present, but the datasource requires PostgreSQL and no PostgreSQL schema/service is configured, so live panels are not expected to work. This does not satisfy the brief's Grafana acceptance checks.

SNS and Bedrock are not implemented. Latency does not trigger incidents. Recovery currently occurs on the next successful check, rather than a configurable recovery threshold. Scheduler state is in-process and unsuitable for multiple API workers/instances.

## Next best improvements

1. Move persistence to PostgreSQL with Alembic migrations, then validate the app and Grafana against a clean database.
2. Add service tests for auth, ownership, SSRF, timeout/status classification, persistence, scheduler, and incident transitions.
3. Add worker-level global limits/distributed locking, rate limits, session lifetime management, and production network controls.
4. Verify a locked-down EC2 + RDS deployment, secrets injection, CloudWatch logs/metrics, and live Grafana panels.

See `docs/POST_MVP_BACKLOG.md` for the full backlog.
