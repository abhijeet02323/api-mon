# SentinelAPI

SentinelAPI is a self-hosted API monitoring. It checks HTTP endpoints on a schedule, stores check history and incidents in SQLite, and provides a browser dashboard and JSON API. It also supports chained API scenarios, Prometheus metrics, and optional Amazon Bedrock powered assistance.

## Features

- Account registration and login with a browser dashboard.
- Scheduled and manual HTTP availability checks with accepted status codes, timeout and optional latency threshold.
- Check history, latency charts, and incidents with acknowledgement and resolution controls.
- Scenario tests with GET, HEAD, POST, PUT, PATCH, and DELETE requests; JSON assertions; extracted values; and up to 10 chained steps per case.
- Prometheus metrics and an optional preconfigured Grafana dashboard.
- Optional Bedrock incident summaries and per-monitor AI Assist conversations.

## Requirements

- Python 3.12 or newer and pip for local development.
- Docker Engine and the Docker Compose plugin for the container setup.
- Network access from the application to the public endpoints you monitor.

The local application does not require AWS credentials or a separate database. SQLite is created automatically on startup.

## Run locally

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Set a unique `APP_SECRET_KEY` in `.env`, then start the application:

```sh
python -m uvicorn app:app --reload
```

Open <http://localhost:8000>, choose **Open dashboard**, and register an account. Passwords must be at least 10 characters. The dashboard is also at <http://localhost:8000/dashboard>.

Useful endpoints:

| Path | Purpose |
| --- | --- |
| `/` | Product home page |
| `/dashboard` | Monitoring dashboard |
| `/docs` | Interactive API documentation |
| `/health` | Liveness check |
| `/ready` | SQLite readiness check |
| `/metrics` | Prometheus text metrics |

The default database file is `sentinelapi.db` in the working directory. Set `DATABASE_PATH` to change it. Keep a copy of this file to back up local users, monitors, results, incidents, and scenario definitions.

## Create and schedule a monitor

Create a monitor in the dashboard with a descriptive name and a public HTTP or HTTPS URL. The checker sends GET requests. You can select one or more accepted HTTP status codes, set a timeout and optional latency threshold, and choose a schedule:

- `interval`: repeat at the configured interval (default minimum 60 seconds).
- `daily`: run at a selected clock time and IANA timezone.
- `once`: run at a selected date and time with a timezone offset.
- `never`: disable automatic runs; manual checks remain available.

Monitors can be paused and resumed. A monitor check reports `UP`, `DEGRADED`, `DOWN`, `TIMEOUT`, `ERROR`, or `VALIDATION_FAILED`. A latency threshold can mark a successful HTTP response as degraded. Two consecutive availability failures open a deduplicated incident; a later passing check resolves it automatically. Incidents can also be acknowledged or resolved in the dashboard.

## Scenario tests

Add a test case from a monitor's detail view. A case has its own target URL, HTTP method, expected status, timeout, optional latency threshold, headers, request body, JSON assertions, extraction rules, and up to 10 additional chained steps. Up to 25 cases can be attached to one monitor. Enabled cases run with their monitor's scheduled suite; use **Run case** to run an individual case immediately.

Example assertions:

```json
[
  {"path": "status", "operator": "equals", "value": "ok"},
  {"path": "data.items[0].id", "operator": "exists"},
  {"path": "data.count", "operator": "gte", "value": 1}
]
```

Supported operators are `equals`, `not_equals`, `contains`, `gt`, `gte`, `lt`, `lte`, `exists`, and `not_exists`. Extraction rules map variable names to JSON paths, for example `{"access_token":"token","item_id":"data.id"}`. Later step URLs, headers, and bodies can use `{{access_token}}` or `{{item_id}}`.

Write methods (POST, PUT, PATCH, DELETE) require explicit mutation opt-in when a case is configured. A manual run containing writes also requires confirmation. Scheduling write cases requires the separate **Allow write steps to run automatically** opt-in. Use isolated, idempotent targets for scheduled writes.

Scenario targets are restricted to public addresses, redirects are disabled, and targets are revalidated before requests. Request bodies are limited to 32 KiB; response bodies used for assertions and extraction are limited to 256 KiB and are not persisted. Hop-by-hop and proxy headers are rejected. Do not put credentials in URLs or literal secrets in saved request body templates. Reference secrets from the app environment instead, for example use `env:SENTINEL_SECRET_API_TOKEN` as a header value or `{{env:SENTINEL_SECRET_PASSWORD}}` in a body template. Define the corresponding `SENTINEL_SECRET_*` variable in the process or `.env` environment; secret values are not saved in SQLite.

## Docker Compose, Prometheus, and Grafana

```sh
cp .env.example .env
```

Set a unique `APP_SECRET_KEY` and `GRAFANA_ADMIN_PASSWORD`, then run:

```sh
docker compose up --build
```

Services are available at:

| Service | Address |
| --- | --- |
| SentinelAPI | <http://localhost:8000> |
| Grafana | <http://localhost:3000> |
| Prometheus | <http://localhost:9090> |

Grafana and Prometheus bind to localhost. Compose provisions the Prometheus data source and SentinelAPI dashboard; Prometheus scrapes `/metrics` every 15 seconds. Named volumes preserve application, Grafana, and Prometheus data. Grafana metrics are scrape-based and do not replace the detailed check history in SentinelAPI. Stop the stack with Ctrl+C or `docker compose down`; `docker compose down -v` also removes its named data volumes.

## Configuration

The application loads `.env` for local runs. Docker Compose passes the project `.env` to the app container. Main settings in `.env.example`:

| Variable | Default | Description |
| --- | --- | --- |
| `APP_ENV` | `development` | Set to `production` to mark the session cookie Secure. |
| `APP_SECRET_KEY` | Placeholder | Replace with a long random value and keep it private. |
| `SESSION_COOKIE_SECURE` | `false` | Set to `true` when HTTPS terminates at a proxy and `APP_ENV` is not production. |
| `DATABASE_PATH` | `./sentinelapi.db` | SQLite database path; Compose overrides this to `/data/sentinelapi.db`. |
| `CHECK_INTERVAL_MIN_SECONDS` | `60` | Minimum monitor interval. |
| `CHECK_TIMEOUT_MAX_SECONDS` | `20` | Maximum check timeout. |
| `GRAFANA_ADMIN_USER` | `admin` | Grafana admin user for Compose. |
| `GRAFANA_ADMIN_PASSWORD` | Placeholder | Change before starting Grafana. |
| `AWS_REGION` | `ap-south-1` | AWS region for optional Bedrock features. |
| `BEDROCK_MODEL_ID` | Placeholder | For Nova Micro in the APAC region, use `apac.amazon.nova-micro-v1:0`. |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Empty | Optional credentials; the standard AWS credential chain or IAM role can also be used. |

## Amazon Bedrock features

AI Assist and incident summaries use Amazon Nova Micro through Bedrock. Configure `AWS_REGION=ap-south-1` and `BEDROCK_MODEL_ID=apac.amazon.nova-micro-v1:0`, then provide AWS credentials through the standard credential chain or the environment variables above. Grant the app identity the permissions in [`iam/bedrock-nova-micro-invoke.json`](iam/bedrock-nova-micro-invoke.json). Without Bedrock configuration, the monitoring dashboard and API continue to work, but AI features are unavailable.

AI Assist saves conversation messages in SQLite per user and monitor. It uses the selected monitor, recent check data, optional incident facts, and recent conversation messages as context. Incident summaries are saved with their incidents. Neither feature calls the monitored endpoint or inspects cloud logs.

## API overview

The versioned JSON API is rooted at `/api/v1`. Login sets an HttpOnly session cookie; send that cookie on authenticated requests. Open `/docs` while the app is running for request and response schemas.

| Area | Routes |
| --- | --- |
| Authentication | `POST /auth/register`, `POST /auth/login`, `POST /auth/logout` |
| Monitors | `GET/POST /monitors`, `GET/PATCH/DELETE /monitors/{id}`, `POST /monitors/{id}/check`, `GET /monitors/{id}/results` |
| Scenarios | `GET/POST /monitors/{id}/test-cases`, `PATCH/DELETE /test-cases/{id}`, `POST /test-cases/{id}/run`, `GET /test-cases/{id}/results` |
| Incidents | `GET /incidents`, `GET /incidents/{id}`, `POST /incidents/{id}/acknowledge`, `POST /incidents/{id}/resolve`, `POST /incidents/{id}/summarize` |
| AI Assist | `POST /ai/assist`, `GET/DELETE /monitors/{id}/ai-chat` |

## Security and deployment notes

Passwords are stored as salted PBKDF2-SHA256 hashes. Browser sessions expire after 12 hours; only a SHA-256 digest of each session token is stored in SQLite. Serve the app over HTTPS in any shared deployment so passwords and cookies are protected in transit. Set `SESSION_COOKIE_SECURE=true` when TLS terminates at a proxy and the app is not in production mode.

Monitor and scenario URLs must use HTTP or HTTPS, contain no URL credentials, and resolve only to globally routable addresses. Private, loopback, reserved, and metadata destinations are rejected. Redirects are disabled. These checks are useful safeguards, but a public deployment should also enforce outbound network controls to reduce DNS rebinding and other server-side request risks. The scheduler runs in-process, so run a single app process for this demo; it does not coordinate schedules between multiple replicas.

## Current scope

- Persistence is SQLite; PostgreSQL support and migrations are not included.
- The scheduler is in-process and does not use a distributed lock or global rate limit.
- Incident notifications such as email or SNS are not implemented.
- Login throttling and email verification are not implemented.
- Scenario tests are not a general browser automation, load testing, fuzzing, or JSON Schema system.
- No AWS deployment configuration is included; Compose is intended for local use.

## Development

Install dependencies as shown above. Run the test suite with:

```sh
python -m unittest discover -s tests -v
```

The project uses FastAPI, SQLite, and Python `unittest`. The dashboard and home page are served from `dashboard.html` and `home.html`.
