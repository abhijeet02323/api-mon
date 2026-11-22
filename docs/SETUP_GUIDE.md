# SentinelAPI basic setup guide

This guide gets the current SentinelAPI demo running on a development machine. The app stores data in a local SQLite file. The optional Grafana dashboard reads app metrics through Prometheus. AWS deployment is not finished.

## What you need

- Python 3.12 or newer
- `pip` (included with most Python installations)
- Git, if you have a writable Git checkout
- Optional: Docker Engine and the Docker Compose plugin
- Outbound internet access from the app for DNS resolution and checks of public endpoints

The app does not require AWS credentials or a separate database for local development.

## 1. Get the project ready

Open a terminal in the project directory. If you have a Git repository, check out or clone the project first. In this workspace, use the directory containing `app.py`.

Create and activate a virtual environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1
```

Install the Python dependencies:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If `python -m pip` is unavailable, install or enable pip for your Python distribution before continuing. The API needs FastAPI, Uvicorn, and httpx from `requirements.txt`.

## 2. Configure local settings

Copy the example settings file:

```sh
cp .env.example .env
```

For a local demo, the defaults are sufficient. Set `APP_SECRET_KEY` to a long random value and change the Grafana password if you plan to start Grafana. Keep `.env` private; it is excluded from Git.

The application loads `.env` automatically for local runs. Docker Compose also supplies the project `.env` through `env_file`. Set `DATABASE_PATH` and the check interval/timeout limits there if you need to change their defaults. For example:

```sh
export DATABASE_PATH=./sentinelapi.db
export CHECK_INTERVAL_MIN_SECONDS=60
export CHECK_TIMEOUT_MAX_SECONDS=20
```

For scenario authentication, export secrets using the `SENTINEL_SECRET_` prefix, for example `export SENTINEL_SECRET_API_TOKEN='Bearer …'`. Scenario definitions store the environment-variable reference, not that value. The request body template itself is saved in SQLite, so use `{{env:SENTINEL_SECRET_PASSWORD}}` instead of typing a password into the template.

To enable incident summaries, set `AWS_REGION=ap-south-1`, `BEDROCK_MODEL_ID=apac.amazon.nova-micro-v1:0`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` in `.env` (add `AWS_SESSION_TOKEN` for temporary credentials), or attach the IAM policy in `iam/bedrock-nova-micro-invoke.json` to the app's AWS identity. The policy allows the APAC inference profile and Nova Micro model. The model is invoked when you select **Analyze with Nova Micro** on an incident.

## 3. Start the API and dashboard

From the project root, run:

```sh
python -m uvicorn app:app --reload
```

Then open:

- Dashboard: <http://localhost:8000>
- Interactive API docs: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/health>
- Database readiness: <http://localhost:8000/ready>
- Basic metrics: <http://localhost:8000/metrics>

The SQLite database is created on first app startup. To use a different path, set `DATABASE_PATH` before starting the app. Stop the server with Ctrl+C.

## 4. Try a monitor

1. On the dashboard, create an account with a valid email and a password of at least 10 characters.
2. Sign in if the page does not sign you in automatically.
3. Add a descriptive name and a public HTTP or HTTPS endpoint that is safe to check with GET.
4. Select **Check now** and review the status and response time.
5. Select the monitor name to view recent checks, failure details, and the latency trend.
6. In the monitor detail view, add a test case with its method, expected status, optional JSON assertions, headers, and body. A chain can extract JSON values and pass them into later steps. Write methods require confirmation and a second opt-in before they can run on schedule.
7. Incidents appear below the monitor list. Login sets an HttpOnly session cookie that expires after 12 hours; sign out revokes the session. API clients should retain and send the cookie securely.

The application rejects credentials in URLs and targets that resolve to local, private, reserved, or metadata IP addresses. Redirects are disabled. The scheduler checks active monitors at their configured interval; the minimum interval defaults to 60 seconds.

## 5. Run with Docker (optional)

Install Docker Engine and the Compose plugin, then run:

```sh
cp .env.example .env
docker compose up --build
```

The API is available on port 8000, Grafana on `http://localhost:3000`, and Prometheus on `http://localhost:9090`. Change `GRAFANA_ADMIN_PASSWORD` in `.env` first. Stop the services with Ctrl+C, or run `docker compose down`. Named volumes keep the app's SQLite file and Grafana state across restarts.

Grafana provisions a Prometheus datasource, and Prometheus scrapes the app's `/metrics` endpoint. This gives a live metrics dashboard while SQLite remains the source of truth for monitor and check history. Detailed history is viewed in the SentinelAPI app/API.

## 6. Run the checks

With dependencies installed, run the small helper tests:

```sh
python -m unittest discover -s tests -v
```

Check Python syntax and Grafana dashboard JSON:

```sh
python -m py_compile app.py
python -c "import json; json.load(open('grafana/dashboards/sentinelapi-overview.json')); print('Dashboard JSON is valid')"
```

The helper tests import the app, so they require the dependencies in `requirements.txt` to be installed first.

## Current scope and next setup work

- **Local demo:** SQLite, API, dashboard, and checks; no AWS account required.
- **Grafana:** local metrics dashboard is configured through Prometheus. Its panels show aggregate metrics, not the full SQLite check history.
- **PostgreSQL:** not used by the current app. Add PostgreSQL support and migrations only if managed/shared persistence is needed.
- **AWS:** not deployed. A real deployment needs AWS account access, a private RDS database, an EC2 instance or other compute, IAM roles, secret injection, TLS, and CloudWatch configuration. Keep the database private and restrict outbound traffic from the checker.
- **Production readiness:** enable HTTPS/TLS and the Secure cookie flag, add login and manual-check rate limits, email verification, stronger SSRF controls such as controlled egress, and a dedicated scheduler/worker before exposing the service publicly.

For implementation status and known issues, see [IMPLEMENTATION_REPORT.md](IMPLEMENTATION_REPORT.md). For planned follow-up work, see [POST_MVP_BACKLOG.md](POST_MVP_BACKLOG.md).
