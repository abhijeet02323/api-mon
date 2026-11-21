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

Open <http://localhost:8000>, create an account with a password of at least 10 characters, and add a public HTTP(S) GET endpoint. Select a monitor name to open its recent check history and response-time chart. API docs are at `/docs`; liveness and database readiness are `/health` and `/ready`. Data is stored in `sentinelapi.db` by default. The first check is manual; active monitors are subsequently checked at their configured interval (minimum 60 seconds).

## Docker and Grafana

```sh
cp .env.example .env
docker compose up --build
```

The app is at port 8000, Grafana binds to localhost port 3000, and Prometheus is at localhost port 9090. Set a unique `GRAFANA_ADMIN_PASSWORD` before starting. Prometheus scrapes `/metrics`; Grafana provisions its Prometheus datasource and dashboard automatically. The dashboard shows monitor states, counts, incidents, and recorded latency summaries. Detailed check history remains available through SentinelAPI because Grafana does not query SQLite directly.

## Configuration and security

See `.env.example`. The application uses a random opaque bearer session token and PBKDF2 password hashes. Monitor targets must resolve exclusively to globally routable addresses; private, loopback, reserved and metadata addresses are rejected, redirects are disabled, and no custom headers or bodies are accepted. Checks use bounded timeouts and do not persist response bodies. Use HTTPS behind a reverse proxy for any shared deployment; this local MVP has no login throttling, CSRF surface is limited to bearer-authenticated API calls, and sessions have no expiry/revocation endpoint. DNS rebinding protection requires an egress proxy/network policy in production.

## AWS status

No AWS deployment was performed. The brief's EC2/RDS/IAM/Secrets Manager/CloudWatch path needs account access and a PostgreSQL backend. Do not expose this demo directly to the internet. Deploy behind TLS and network egress controls; use least-privilege instance roles and injected secrets. ECS/ALB is a post-MVP migration.

## Known limitations

- SQLite is for local demonstration; PostgreSQL migrations and database-backed Grafana integration remain unfinished.
- One in-process scheduler runs per application process, does not use a distributed lock, and has no concurrency/rate cap beyond per-monitor overlap prevention.
- Incident opening uses two consecutive availability failures; recovery is on the next successful result. Latency degradation does not currently open incidents.
- SNS and Bedrock are not implemented. AI is disabled/not available.
- Login/manual-check rate limits, session expiry, email verification, and deployment hardening remain backlog items.

See `docs/POST_MVP_BACKLOG.md` and `docs/IMPLEMENTATION_REPORT.md` for the detailed review.
