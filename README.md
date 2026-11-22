# SentinelAPI

SentinelAPI is a small API availability monitoring MVP. It has a FastAPI REST API, browser dashboard, SQLite persistence for local/demo use, scheduled GET checks, check history, and deterministic incidents. Grafana provisioning artifacts are included. This empty starter checkout did not provide AWS credentials or a PostgreSQL service, so those deployment paths have not been verified.

## Run locally

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app:app --reload
```

Open <http://localhost:8000>, create an account with a password of at least 10 characters, and add a public HTTP(S) GET endpoint. Monitors accept one or more expected HTTP status codes; a check passes if the response matches any accepted code. Edit a monitor to set these codes and schedule checks at its interval, daily at a selected local time, once at a selected local date and time, or never; manual checks remain available. The dashboard also includes status totals, search and status filters, pause/resume and delete controls, incident acknowledgement and resolution, and monitor history with response-time charts. API docs are at `/docs`; liveness and database readiness are `/health` and `/ready`. Data is stored in `sentinelapi.db` by default. Active monitors are checked on their configured schedule.

## Docker and Grafana

```sh
cp .env.example .env
docker compose up --build
```

The app is at port 8000, Grafana binds to localhost port 3000, and Prometheus is at localhost port 9090. Set a unique `GRAFANA_ADMIN_PASSWORD` before starting. Prometheus scrapes `/metrics`; Grafana provisions its Prometheus datasource and dashboard automatically. The dashboard shows monitor states, counts, incidents, and recorded latency summaries. Detailed check history remains available through SentinelAPI because Grafana does not query SQLite directly.

## Scenario-based API tests

Open a monitor's detail view and choose **Add test case** to create a scenario. A case has its own URL, method, expected status, timeout, optional latency threshold, request headers/body, JSON assertions, and up to 10 chained steps. Up to 25 cases can be attached to a monitor. Enabled safe cases run with that monitor's schedule; **Run case** executes one immediately and shows each step's result.

Assertions use simple JSON paths and explicit operators. For example:

```json
[
  {"path": "status", "operator": "equals", "value": "ok"},
  {"path": "data.items[0].id", "operator": "exists"},
  {"path": "data.count", "operator": "gte", "value": 1}
]
```

Supported methods are GET, HEAD, POST, PUT, PATCH, and DELETE. Supported assertion operators are `equals`, `not_equals`, `contains`, `gt`, `gte`, `lt`, `lte`, `exists`, and `not_exists`. A step can extract response JSON paths into variables (for example `{"access_token":"token","item_id":"data.id"}`); later URLs, headers, and bodies can refer to them as `{{access_token}}`. Use `env:SENTINEL_SECRET_NAME` for a sensitive header or `{{env:SENTINEL_SECRET_NAME}}` in a request body. Secret values must be set in the app environment and are not stored in SQLite. Request body templates are stored, so do not put literal credentials in them or secrets in URL query strings.

Write methods require explicit confirmation when saving and again for each manual run. They stay out of the scheduler unless **Allow write steps to run automatically** is explicitly enabled. Keep scheduled write tests isolated and idempotent. Redirects are disabled, custom hop-by-hop/proxy headers are rejected, each request target is revalidated, request bodies are limited to 32 KiB, and response bodies used for assertions/extraction are capped at 256 KiB and never persisted. Outcomes are `UP`, `DEGRADED`, `DOWN`, `TIMEOUT`, `ERROR`, and `VALIDATION_FAILED`; two consecutive failures open a deduplicated incident and two passing runs resolve it.

This is an extensible scenario runner, not a universal API test language. It currently does not provide browser execution, arbitrary schema/JSON Schema validation, loops, branching, load testing, fuzzing, or multi-region execution. Request body templates are stored in the local SQLite database; use environment references for credentials and review access to that file.

## Configuration and security

See `.env.example`. Configure sensitive values using `SENTINEL_SECRET_*` environment variables (Docker Compose reads the project `.env`; local shell runs need exported values). Passwords are stored as salted PBKDF2-SHA256 hashes (never encrypted or recoverable). Browser login uses a 12-hour HttpOnly, SameSite=Strict session cookie; only a SHA-256 digest of the session token is stored in SQLite. Production mode sets the cookie's Secure flag; serve the app behind HTTPS/TLS so credentials and session cookies are encrypted in transit. Set `SESSION_COOKIE_SECURE=true` when TLS terminates at a proxy but `APP_ENV` is not `production`. Sign-out revokes the current session. Monitor targets must resolve exclusively to globally routable addresses; private, loopback, reserved and metadata addresses are rejected and redirects are disabled. Login throttling, email verification, and DNS rebinding protection via an egress proxy/network policy remain deployment hardening needs.

## AWS status

No AWS deployment was performed. The brief's EC2/RDS/IAM/Secrets Manager/CloudWatch path needs account access and a PostgreSQL backend. Do not expose this demo directly to the internet. Deploy behind TLS and network egress controls; use least-privilege instance roles and injected secrets. ECS/ALB is a post-MVP migration.

## Known limitations

- SQLite is for local demonstration; PostgreSQL migrations and database-backed Grafana integration remain unfinished.
- One in-process scheduler runs per application process, does not use a distributed lock, and has no concurrency/rate cap beyond per-monitor overlap prevention.
- Incident opening uses two consecutive availability failures; recovery is on the next successful result. Latency degradation does not currently open incidents.
- SNS and Bedrock are not implemented. AI is disabled/not available.
- Login/manual-check rate limits, email verification, and deployment hardening remain backlog items.

See `docs/POST_MVP_BACKLOG.md` and `docs/IMPLEMENTATION_REPORT.md` for the detailed review.
