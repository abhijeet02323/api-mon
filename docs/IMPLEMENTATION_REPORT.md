# SentinelAPI implementation report

## Delivered

- FastAPI REST service with OpenAPI, health/readiness endpoints, and a minimal browser dashboard.
- Account registration/login with salted PBKDF2 password hashes and opaque bearer sessions.
- Owner-scoped monitor create/list/detail/update/delete, manual check, history, incidents, acknowledgement, and resolution endpoints.
- Dashboard monitor detail view with recent check history, failure details, and an inline response-time trend chart.
- SQLite persistence, a one-process periodic scheduler, per-monitor overlap prevention, bounded request timeout, disabled redirects, and no response-body persistence.
- DNS/IP checks block non-global destinations before monitor creation and before each request. Incidents open after two consecutive availability failures and resolve after a successful check.
- Docker app/Prometheus/Grafana setup, an example metrics dashboard and datasource provisioning, environment template, backlog, and this report.

## Architecture and run instructions

FastAPI + httpx + SQLite in one container, with an in-process asyncio scheduler. Prometheus scrapes app metrics and Grafana visualizes them in separate Compose services. Start with `cp .env.example .env && docker compose up --build`. See the root README for account setup and usage.

## Verification

- `python -m py_compile app.py`: passed after fixing a syntax error found during initial validation.
- Grafana dashboard JSON parsing with Python's `json` module: passed.
- Dashboard inline JavaScript syntax check with `node --check`: passed for monitor history and latency chart code.
- FastAPI/httpx runtime and endpoint tests: blocked. `python -m unittest discover -s tests -v` cannot import the app because `httpx` is not installed; `python -m pip` is unavailable in this environment, so dependencies could not be installed.
- UI → API → DB → result path, scheduler behavior, and incident transitions: not runtime verified.
- Docker Compose and live Grafana datasource: configured but not runtime verified because Docker is unavailable in the build environment. PostgreSQL is not used. AWS deployment and CloudWatch: not verified; no AWS credentials are available in this checkout.
- Git history/status: history is available, but this update could not be committed because the workspace marks `.git` read-only (`git add` cannot create `.git/index.lock`). Runtime tests remain blocked by the missing Python dependencies.

## Security review

Positive controls: password hashing, bearer auth, parameterized SQLite queries, ownership-scoped reads/updates/deletes, URL scheme and credential validation, public-IP-only DNS validation, redirect disabling, bounded request timeout, bounded input fields, and response-body omission.

Known gaps: no login or manual-check rate limiting, session expiry/revocation, TLS termination, database migrations, DNS pinning/egress proxy, global scheduler concurrency/rate limiting, or production CORS/security-header configuration. `is_global` checks reduce SSRF exposure but cannot stop DNS rebinding between resolution and connection. Do not expose this MVP to the public internet without network egress controls and a hardened deployment.

## Deployment and product gaps

AWS deployment was not attempted. The brief's P0 PostgreSQL requirement is not met: SQLite was selected to keep this starter checkout self-contained. Grafana is configured to display live app metrics through Prometheus, but the stack was not started here, so datasource health and panel data have not been verified. Grafana does not query individual SQLite check history.

SNS and Bedrock are not implemented. Latency does not trigger incidents. Recovery currently occurs on the next successful check, rather than a configurable recovery threshold. Scheduler state is in-process and unsuitable for multiple API workers/instances.

## Next best improvements

1. Move persistence to PostgreSQL with Alembic migrations, then validate the app and Grafana against a clean database.
2. Add service tests for auth, ownership, SSRF, timeout/status classification, persistence, scheduler, and incident transitions.
3. Add worker-level global limits/distributed locking, rate limits, session lifetime management, and production network controls.
4. Verify a locked-down EC2 + RDS deployment, secrets injection, CloudWatch logs/metrics, and live Grafana panels.

See `docs/POST_MVP_BACKLOG.md` for the full backlog.
